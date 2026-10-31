from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.core.models import AuditEvent, PlatformAnnouncement
from apps.operations.services import round_usd
from apps.subscriptions.models import (
    BillingCycle,
    PaymentStatus,
    Plan,
    SubscriptionPayment,
    SubscriptionStatus,
    TenantSubscription,
)
from apps.subscriptions.serializers import (
    PaymentReconcileSerializer,
    PublicPlanSerializer,
    PublicTenantRegistrationSerializer,
    TenantStatusActionSerializer,
)
from apps.tenants.models import Tenant, TenantMembership, TenantRole, TenantStatus
from apps.tenants.permissions import (
    IsPlatformSuperAdmin,
    IsPlatformSuperAdminOrSupportReadOnly,
)

User = get_user_model()


def ensure_default_plans() -> None:
    """Seeds default SaaS plans if none exist yet."""
    if Plan.objects.exists():
        return
    Plan.objects.bulk_create(
        [
            Plan(
                code="starter",
                name_en="Starter Print Shop",
                name_km="កញ្ចប់ចាប់ផ្ដើមអាជីវកម្ម",
                description_en="Essential quotation, order, and invoicing tools for small print shops.",
                description_km="មុខងារចេញសម្រង់តម្លៃ បញ្ជាទិញ និងវិក្កយបត្រសម្រាប់រោងពុម្ពខ្នាតតូច។",
                monthly_price_usd=Decimal("29.00"),
                annual_price_usd=Decimal("290.00"),
                max_staff_users=5,
                max_orders_per_month=300,
                sort_order=1,
            ),
            Plan(
                code="growth",
                name_en="Growth Printing Press",
                name_km="កញ្ចប់ពង្រីកអាជីវកម្ម",
                description_en="Full production workflow, material ledger, and multi-staff RBAC.",
                description_km="ប្រព័ន្ធគ្រប់គ្រងផលិតកម្ម ស្តុកវត្ថុធាតុដើម និងបែងចែកសិទ្ធិបុគ្គលិកពេញលេញ។",
                monthly_price_usd=Decimal("59.00"),
                annual_price_usd=Decimal("590.00"),
                max_staff_users=20,
                max_orders_per_month=2000,
                sort_order=2,
            ),
            Plan(
                code="enterprise",
                name_en="Enterprise Industrial Press",
                name_km="កញ្ចប់រោងពុម្ពឧស្សាហកម្ម",
                description_en="High-volume printing operations, priority support, and full analytics.",
                description_km="សម្រាប់រោងពុម្ពខ្នាតធំ មានបរិមាណការងារច្រើន និងរបាយការណ៍ហិរញ្ញវត្ថុលម្អិត។",
                monthly_price_usd=Decimal("119.00"),
                annual_price_usd=Decimal("1190.00"),
                max_staff_users=100,
                max_orders_per_month=20000,
                sort_order=3,
            ),
        ]
    )


class PublicPlanListAPIView(APIView):
    """Frontend C: Lists public subscription plans."""

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        ensure_default_plans()
        plans = Plan.objects.filter(is_public=True)
        return Response(PublicPlanSerializer(plans, many=True).data)


class PublicTenantRegistrationAPIView(APIView):
    """
    REQ-SAAS-01 & REQ-SAAS-03:
    Frontend C endpoint for prospective printing businesses to register and submit
    an initial subscription checkout request. Supports idempotency keys.
    """

    permission_classes = [AllowAny]
    throttle_scope = "auth_register" 

    @transaction.atomic
    def post(self, request: Request) -> Response:
        ensure_default_plans()
        serializer = PublicTenantRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Idempotency check: if payment with this key already exists, return existing state
        existing_payment = (
            SubscriptionPayment.objects.select_related("tenant", "subscription__plan")
            .filter(idempotency_key=data["idempotency_key"])
            .first()
        )
        if existing_payment:
            return Response(
                {
                    "idempotent_replay": True,
                    "tenant_id": str(existing_payment.tenant.id),
                    "tenant_slug": existing_payment.tenant.slug,
                    "tenant_status": existing_payment.tenant.status,
                    "subscription_status": existing_payment.subscription.status,
                    "payment_id": str(existing_payment.id),
                    "payment_status": existing_payment.status,
                    "amount_usd": str(existing_payment.amount_usd),
                },
                status=status.HTTP_200_OK,
            )

        email = data["email"].lower().strip()
        if User.objects.filter(email=email).exists():
            return Response(
                {"detail": "An account with this email already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if Tenant.objects.filter(slug=data["business_slug"]).exists():
            return Response(
                {"detail": "This business slug is already taken."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plan = get_object_or_404(Plan, code=data["plan_code"], is_public=True)

        owner = User.objects.create_user(
            email=email,
            password=data["password"],
            full_name=data["full_name"],
            phone=data["phone"],
        )

        tenant = Tenant.objects.create(
            name=data["business_name"],
            slug=data["business_slug"],
            status=TenantStatus.PENDING_REVIEW,
            phone=data["phone"],
            email=email,
        )

        TenantMembership.objects.create(
            tenant=tenant,
            user=owner,
            role=TenantRole.TENANT_OWNER,
            is_active=True,
        )

        amount = (
            plan.annual_price_usd
            if data["billing_cycle"] == BillingCycle.ANNUAL
            else plan.monthly_price_usd
        )

        subscription = TenantSubscription.objects.create(
            tenant=tenant,
            plan=plan,
            billing_cycle=data["billing_cycle"],
            status=SubscriptionStatus.PENDING_PAYMENT,
        )

        payment = SubscriptionPayment.objects.create(
            tenant=tenant,
            subscription=subscription,
            amount_usd=amount,
            provider=data["payment_provider"],
            provider_reference=data["provider_reference"],
            idempotency_key=data["idempotency_key"],
            status=PaymentStatus.PENDING,
        )

        AuditEvent.objects.create(
            actor_user=owner,
            tenant=tenant,
            event_type="SAAS_TENANT_REGISTERED",
            target_model="tenants.Tenant",
            target_id=str(tenant.id),
            metadata={
                "plan_code": plan.code,
                "billing_cycle": data["billing_cycle"],
                "payment_id": str(payment.id),
                "amount_usd": str(amount),
            },
        )

        return Response(
            {
                "idempotent_replay": False,
                "tenant_id": str(tenant.id),
                "tenant_slug": tenant.slug,
                "tenant_status": tenant.status,
                "subscription_status": subscription.status,
                "payment_id": str(payment.id),
                "payment_status": payment.status,
                "amount_usd": str(payment.amount_usd),
            },
            status=status.HTTP_201_CREATED,
        )


class SuperAdminOverviewAPIView(APIView):
    """Frontend A: Platform operational health, tenant metrics, and revenue summary."""

    permission_classes = [IsAuthenticated, IsPlatformSuperAdminOrSupportReadOnly]

    def get(self, request: Request) -> Response:
        from apps.operations.models import SalesOrder

        total_tenants = Tenant.objects.count()
        active_tenants = Tenant.objects.filter(status=TenantStatus.ACTIVE).count()
        pending_tenants = Tenant.objects.filter(status=TenantStatus.PENDING_REVIEW).count()
        pending_payments = SubscriptionPayment.objects.filter(status=PaymentStatus.PENDING).count()
        total_revenue = round_usd(
            SubscriptionPayment.objects.filter(status=PaymentStatus.SUCCEEDED).aggregate(
                total=Sum("amount_usd")
            )["total"]
            or Decimal("0.00")
        )

        active_subs = TenantSubscription.objects.filter(status=SubscriptionStatus.ACTIVE).select_related("plan")
        mrr = Decimal("0.00")
        for sub in active_subs:
            if sub.billing_cycle == BillingCycle.ANNUAL:
                mrr += sub.plan.annual_price_usd / Decimal("12")
            else:
                mrr += sub.plan.monthly_price_usd

        total_orders = SalesOrder.objects.count()
        now = timezone.now()
        churn_risk_count = TenantSubscription.objects.filter(
            status=SubscriptionStatus.ACTIVE,
            current_period_end__lte=now + timedelta(days=7),
            current_period_end__gte=now,
        ).count()
        active_announcements_count = PlatformAnnouncement.objects.filter(is_active=True).count()

        recent_audits = [
            {
                "id": str(ev.id),
                "created_at": ev.created_at.isoformat(),
                "event_type": ev.event_type,
                "target_model": ev.target_model,
                "target_id": ev.target_id,
                "metadata": ev.metadata,
            }
            for ev in AuditEvent.objects.all()[:10]
        ]

        return Response(
            {
                "metrics": {
                    "total_tenants": total_tenants,
                    "active_tenants": active_tenants,
                    "pending_tenants": pending_tenants,
                    "pending_payments": pending_payments,
                    "total_revenue_usd": str(total_revenue),
                    "mrr_usd": str(round_usd(mrr)),
                    "total_orders": total_orders,
                    "churn_risk_count": churn_risk_count,
                    "active_announcements_count": active_announcements_count,
                },
                "recent_audit_events": recent_audits,
            }
        )


class SuperAdminTenantListAPIView(APIView):
    """Frontend A: Lists all tenants with subscription and pending payment details."""

    permission_classes = [IsAuthenticated, IsPlatformSuperAdminOrSupportReadOnly]

    def get(self, request: Request) -> Response:
        tenants = Tenant.objects.select_related("subscription__plan").prefetch_related(
            "subscription_payments"
        )
        results = []
        for t in tenants:
            sub = getattr(t, "subscription", None)
            latest_payment = t.subscription_payments.first()
            results.append(
                {
                    "id": str(t.id),
                    "name": t.name,
                    "slug": t.slug,
                    "status": t.status,
                    "email": t.email,
                    "phone": t.phone,
                    "created_at": t.created_at.isoformat(),
                    "subscription": {
                        "plan_code": sub.plan.code,
                        "plan_name_en": sub.plan.name_en,
                        "status": sub.status,
                        "billing_cycle": sub.billing_cycle,
                    }
                    if sub
                    else None,
                    "latest_payment": {
                        "id": str(latest_payment.id),
                        "amount_usd": str(latest_payment.amount_usd),
                        "status": latest_payment.status,
                        "provider": latest_payment.provider,
                        "provider_reference": latest_payment.provider_reference,
                    }
                    if latest_payment
                    else None,
                }
            )
        return Response(results)


class SuperAdminPaymentReconcileAPIView(APIView):
    """
    Frontend A: Reconciles (APPROVE / REJECT) a SubscriptionPayment and transitions
    Tenant + TenantSubscription lifecycle atomically.
    """

    permission_classes = [IsAuthenticated, IsPlatformSuperAdmin]

    @transaction.atomic
    def post(self, request: Request, payment_id: str) -> Response:
        serializer = PaymentReconcileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment = get_object_or_404(
            SubscriptionPayment.objects.select_for_update().select_related(
                "tenant", "subscription"
            ),
            id=payment_id,
        )

        if payment.status == PaymentStatus.SUCCEEDED:
            return Response(
                {"detail": "Payment is already reconciled as SUCCEEDED."},
                status=status.HTTP_200_OK,
            )

        action = serializer.validated_data["action"]
        notes = serializer.validated_data["notes"]
        now = timezone.now()

        if action == "APPROVE":
            payment.status = PaymentStatus.SUCCEEDED
            payment.verified_by = request.user
            payment.verified_at = now
            payment.notes = notes
            payment.save()

            sub = payment.subscription
            sub.status = SubscriptionStatus.ACTIVE
            sub.current_period_start = now
            days = 365 if sub.billing_cycle == BillingCycle.ANNUAL else 30
            sub.current_period_end = now + timedelta(days=days)
            sub.save()

            tenant = payment.tenant
            tenant.status = TenantStatus.ACTIVE
            tenant.save(update_fields=["status", "updated_at"])

            from apps.operations.preset_service import seed_tenant_master_presets
            seed_tenant_master_presets(tenant=tenant, actor_user=request.user)

            event_type = "SAAS_PAYMENT_APPROVED_TENANT_ACTIVATED"
        else:
            payment.status = PaymentStatus.REJECTED
            payment.verified_by = request.user
            payment.verified_at = now
            payment.notes = notes
            payment.save()
            event_type = "SAAS_PAYMENT_REJECTED"

        AuditEvent.objects.create(
            actor_user=request.user,
            tenant=payment.tenant,
            event_type=event_type,
            target_model="subscriptions.SubscriptionPayment",
            target_id=str(payment.id),
            metadata={"action": action, "amount_usd": str(payment.amount_usd)},
        )

        return Response(
            {
                "payment_id": str(payment.id),
                "payment_status": payment.status,
                "tenant_status": payment.tenant.status,
                "subscription_status": payment.subscription.status,
            }
        )


class SuperAdminTenantStatusAPIView(APIView):
    """Frontend A: Suspend or Reactivate a tenant with mandatory audit logging."""

    permission_classes = [IsAuthenticated, IsPlatformSuperAdmin]

    @transaction.atomic
    def post(self, request: Request, tenant_id: str) -> Response:
        serializer = TenantStatusActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tenant = get_object_or_404(Tenant.objects.select_for_update(), id=tenant_id)
        subscription = (
            TenantSubscription.objects.select_for_update()
            .filter(tenant=tenant)
            .first()
        )
        action = serializer.validated_data["action"]
        reason = serializer.validated_data["reason"]

        if action == "SUSPEND":
            tenant.status = TenantStatus.SUSPENDED
            if subscription is not None:
                subscription.status = SubscriptionStatus.SUSPENDED
                subscription.save(update_fields=["status", "updated_at"])
        else:
            now = timezone.now()
            if subscription is None:
                raise ValidationError(
                    "Cannot activate a tenant without a subscription. "
                    "Reconcile a valid subscription payment first."
                )
            if subscription.status != SubscriptionStatus.SUSPENDED:
                raise ValidationError(
                    "Only a suspended subscription can be reactivated through this endpoint. "
                    "Use payment reconciliation for pending, past-due, or canceled subscriptions."
                )
            if (
                subscription.current_period_end is None
                or subscription.current_period_end <= now
            ):
                raise ValidationError(
                    "Cannot reactivate an expired subscription. "
                    "Approve a valid subscription payment to renew its billing period."
                )

            subscription.status = SubscriptionStatus.ACTIVE
            update_fields = ["status", "updated_at"]
            if subscription.current_period_start is None:
                subscription.current_period_start = now
                update_fields.append("current_period_start")
            subscription.save(update_fields=update_fields)
            tenant.status = TenantStatus.ACTIVE

        tenant.save(update_fields=["status", "updated_at"])

        AuditEvent.objects.create(
            actor_user=request.user,
            tenant=tenant,
            event_type=f"SUPER_ADMIN_TENANT_{action}",
            target_model="tenants.Tenant",
            target_id=str(tenant.id),
            metadata={"reason": reason},
        )
        return Response(
            {
                "tenant_id": str(tenant.id),
                "status": tenant.status,
                "subscription_status": subscription.status if subscription else None,
            }
        )


class SuperAdminUsbLicenseVerifyAPIView(APIView):
    """
    Frontend A: Verifies physical SuperAdmin USB Flash Drive hardware license.dat token.
    Validates digital signature, physical volume serial hardware binding, expiry, and revocation.
    """

    permission_classes = [IsAuthenticated, IsPlatformSuperAdmin]

    def post(self, request: Request) -> Response:
        from apps.core.usb_licensing import (
            issue_elevated_usb_jwt,
            validate_usb_license,
        )

        license_data = request.data.get("license_data")
        hardware_fingerprint = request.data.get("hardware_fingerprint")

        if not isinstance(license_data, dict) or not isinstance(hardware_fingerprint, dict):
            return Response(
                {"detail": "Request must include 'license_data' and 'hardware_fingerprint' objects."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_valid, reason = validate_usb_license(
            license_data=license_data,
            hardware_fingerprint=hardware_fingerprint,
            expected_user_email=request.user.email,
        )

        ip_address = request.META.get("REMOTE_ADDR")

        if not is_valid:
            AuditEvent.objects.create(
                actor_user=request.user,
                event_type="SUPERADMIN_USB_LICENSE_REJECTED",
                target_model="core.UsbLicense",
                target_id=str(license_data.get("license_id", "UNKNOWN")),
                ip_address=ip_address,
                metadata={"reason": reason, "email": request.user.email},
            )
            return Response(
                {"detail": f"USB License Verification Failed: {reason}"},
                status=status.HTTP_403_FORBIDDEN,
            )

        session_id = getattr(request.auth, "id", None) or str(uuid.uuid4())
        elevation_data = issue_elevated_usb_jwt(
            user=request.user,
            session_id=str(session_id),
            license_id=license_data["license_id"],
        )

        AuditEvent.objects.create(
            actor_user=request.user,
            event_type="SUPERADMIN_USB_LICENSE_VERIFIED",
            target_model="core.UsbLicense",
            target_id=license_data["license_id"],
            ip_address=ip_address,
            metadata={
                "volume_serial": hardware_fingerprint.get("volume_serial_number"),
                "expires_at": license_data.get("expires_at"),
            },
        )

        return Response(
            {
                "status": "verified",
                "license_id": license_data["license_id"],
                "issued_to": license_data["issued_to_email"],
                "expires_at": license_data["expires_at"],
                "permissions": license_data.get("permissions", []),
                **elevation_data,
            },
            status=status.HTTP_200_OK,
        )


class SuperAdminUsbLicenseRevokeAPIView(APIView):
    """
    Frontend A: SuperAdmin revokes a compromised or lost USB hardware license key.
    """

    permission_classes = [IsAuthenticated, IsPlatformSuperAdmin]

    def post(self, request: Request) -> Response:
        from apps.core.usb_licensing import revoke_usb_license

        license_id = request.data.get("license_id")
        reason = request.data.get("reason", "Revoked by SuperAdmin")
        if not license_id or not isinstance(license_id, str):
            return Response(
                {"detail": "Mandatory parameter 'license_id' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        revoke_usb_license(
            license_id=license_id.strip(),
            actor_user=request.user,
            reason=reason,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        return Response(
            {"status": "revoked", "license_id": license_id},
            status=status.HTTP_200_OK,
        )


class SuperAdminTenantImpersonateAPIView(APIView):
    """
    SuperAdmin Support Mode:
    Issues a short-lived 15-minute token allowing SuperAdmin to inspect tenant workspace directly.
    Logs SUPERADMIN_TENANT_IMPERSONATED event.
    """

    permission_classes = [IsAuthenticated, IsPlatformSuperAdmin]

    def post(self, request: Request, tenant_id: str) -> Response:
        from apps.accounts.jwt_service import issue_impersonation_token

        try:
            token_payload = issue_impersonation_token(
                superadmin_user=request.user,
                target_tenant_id=tenant_id,
                ip_address=request.META.get("REMOTE_ADDR"),
            )
            return Response(token_payload, status=status.HTTP_200_OK)
        except Tenant.DoesNotExist:
            return Response({"detail": "Tenant not found."}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class SuperAdminTenantSeedPresetsAPIView(APIView):
    """
    1-Click Master Catalog Presets Seeder for Cambodia printing industry.
    Seeds standard paper stocks, wide-format flex banner, waterproof sticker, and default customer.
    """

    permission_classes = [IsAuthenticated, IsPlatformSuperAdmin]

    def post(self, request: Request, tenant_id: str) -> Response:
        from apps.operations.preset_service import seed_tenant_master_presets

        tenant = get_object_or_404(Tenant, id=tenant_id)
        result = seed_tenant_master_presets(tenant=tenant, actor_user=request.user)
        return Response(result, status=status.HTTP_200_OK)

