package me.xennex.live;

import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class RoomAddressTest {
    @Test
    public void acceptsExistingRoomCodesAndLinks() {
        assertEquals("ZEN", RoomAddress.normalize(" zen "));
        assertEquals("XNX-123", RoomAddress.normalize("https://xennex-live.alexdoong11.workers.dev/?room=xnx%2D123"));
        assertEquals("xennex-v3-zen", RoomAddress.coordinator("ZEN"));
    }

    @Test
    public void rejectsMalformedUnboundedOrInjectedInput() {
        String[] invalidInputs = {
            null,
            "",
            "ab",
            "a/b",
            "a b",
            "<script>",
            "https://host/?room=%XX",
            "https://host/?other=ZEN",
            "file:///ZEN",
            "Z".repeat(2049)
        };
        for (String value : invalidInputs) {
            assertEquals("", RoomAddress.normalize(value));
        }
    }

    @Test
    public void linksSupplyOnlyACodeNeverASignalingHost() {
        assertEquals("ZEN", RoomAddress.normalize("https://untrusted.example/?room=ZEN&host=evil"));
        assertEquals("xennex-v3-zen", RoomAddress.coordinator(RoomAddress.normalize("https://untrusted.example/?room=ZEN")));
    }
}
