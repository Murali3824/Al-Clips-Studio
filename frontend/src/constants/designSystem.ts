/**
 * Shared Design System Constants & WYSIWYG Math Utilities.
 *
 * Single source of truth for fixed Hook/Heading component design values
 * and precise scaling math shared between React UI previews and FFmpeg renderers.
 */

export const HOOK_DESIGN_SYSTEM = {
  /** Fixed internal border padding in pixels */
  padding: 12,
  /** Fixed internal border radius in pixels */
  borderRadius: 8,
} as const;

export type HookPosition = 'top-center' | 'top' | 'middle';

export function getHookCardPreviewStyles(
  position: HookPosition | string = 'top-center',
  containerWidth: number = 320,
  containerHeight: number = 568
) {
  // Scale factor relative to 1080p canvas (1080 / 430 ≈ 2.5)
  const scale = containerWidth / 430;
  const paddingPx = Math.round(HOOK_DESIGN_SYSTEM.padding * scale);
  const radiusPx = Math.round(HOOK_DESIGN_SYSTEM.borderRadius * scale);

  let topOffset = '11.4%'; // top-center (~220 / 1920)
  if (position === 'top') {
    topOffset = '7.3%';  // top (~140 / 1920)
  } else if (position === 'middle') {
    topOffset = '45%';   // middle centered
  }

  return {
    paddingPx,
    radiusPx,
    topOffset,
    scale,
  };
}
