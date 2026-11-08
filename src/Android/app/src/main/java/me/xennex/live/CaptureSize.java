package me.xennex.live;

/** Even encoder dimensions, preserve aspect, never upscale. Long edge capped for mobile upload. */
final class CaptureSize {
    private static final double MAX_LONG_EDGE = 1280.0;

    private CaptureSize() {}

    static int[] fit(int width, int height) {
        if (width < 1 || height < 1) {
            throw new IllegalArgumentException("Invalid capture dimensions");
        }
        double scale = Math.min(1.0, MAX_LONG_EDGE / Math.max(width, height));
        int scaledWidth = Math.max(2, ((int) (width * scale) / 2) * 2);
        int scaledHeight = Math.max(2, ((int) (height * scale) / 2) * 2);
        return new int[]{scaledWidth, scaledHeight};
    }
}
