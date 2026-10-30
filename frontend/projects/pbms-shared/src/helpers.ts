export function formatApiErrorMessage(err: any, fallback = 'Operation failed.'): string {
  if (!err) return fallback;
  if (typeof err === 'string') return err;
  if (typeof err.error === 'string') return err.error;
  if (err.error?.detail && typeof err.error.detail === 'string') return err.error.detail;
  if (Array.isArray(err.error?.non_field_errors) && err.error.non_field_errors.length > 0) {
    return err.error.non_field_errors.join(' | ');
  }
  if (Array.isArray(err.error) && err.error.length > 0) {
    return err.error.join(' | ');
  }
  if (typeof err.error === 'object' && err.error !== null) {
    const parts: string[] = [];
    for (const [key, val] of Object.entries(err.error)) {
      if (Array.isArray(val)) {
        parts.push(`${key}: ${val.join(', ')}`);
      } else if (typeof val === 'string') {
        parts.push(`${key}: ${val}`);
      } else if (val && typeof val === 'object') {
        parts.push(`${key}: ${JSON.stringify(val)}`);
      }
    }
    if (parts.length > 0) return parts.join(' | ');
  }
  return err.message || fallback;
}

export function isSubscriptionDenialError(err: any): boolean {
  if (err?.status === 403 || err?.status === 400) {
    const detail = String(
      err?.error?.detail ||
      (typeof err?.error === 'string' ? err?.error : '') ||
      (Array.isArray(err?.error?.non_field_errors) ? err.error.non_field_errors.join(' ') : '') ||
      (Array.isArray(err?.error) ? err.error.join(' ') : '') ||
      err?.message ||
      ''
    ).toLowerCase();
    return (
      detail.includes('subscription') &&
      (detail.includes('billing period') ||
        detail.includes('expired') ||
        detail.includes('not active') ||
        detail.includes('entitlement'))
    );
  }
  return false;
}
