package me.xennex.live;

import org.junit.Test;
import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;

public class CaptureSizeTest {
    @Test
    public void portraitAndLandscapeFitEncoderWithoutUpscaling() {
        assertArrayEquals(new int[]{720, 1280}, CaptureSize.fit(1080, 1920));
        assertArrayEquals(new int[]{1280, 720}, CaptureSize.fit(1920, 1080));
        assertArrayEquals(new int[]{640, 480}, CaptureSize.fit(640, 480));

        int[] size = CaptureSize.fit(1080, 2341);
        assertEquals(0, size[0] % 2);
        assertEquals(0, size[1] % 2);
        assertEquals(1280, size[1]);
    }

    @Test(expected = IllegalArgumentException.class)
    public void refusesInvalidDimensions() {
        CaptureSize.fit(0, 1080);
    }
}
