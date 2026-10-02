/** Framing, not graph semantics. Preserve the desktop composition and fit the
 * entire sphere into the narrower dimension on portrait screens. */
export const SPHERE_CAMERA_FOV = 34;
export const DESKTOP_CAMERA_DISTANCE = 4;
const PORTRAIT_FIT_DISTANCE = 4.15;

export function cameraDistanceForViewport(width: number, height: number): number {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return DESKTOP_CAMERA_DISTANCE;
  }
  return Math.max(DESKTOP_CAMERA_DISTANCE, PORTRAIT_FIT_DISTANCE / (width / height));
}
