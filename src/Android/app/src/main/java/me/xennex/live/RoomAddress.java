package me.xennex.live;

import java.net.URI;
import java.net.URLDecoder;
import java.util.Locale;

/** Room identifiers only: pasted links never select a signaling server. */
public final class RoomAddress {
    private static final int MAX_INPUT_LENGTH = 2048;

    private RoomAddress() {}

    public static String normalize(String input) {
        if (input == null || input.length() > MAX_INPUT_LENGTH) {
            return "";
        }
        String value = input.trim();
        if (value.startsWith("https://") || value.startsWith("http://")) {
            value = extractRoomFromUrl(value);
        }
        value = value.toUpperCase(Locale.ROOT);
        if (!value.matches("[A-Z0-9][A-Z0-9_-]{2,39}")) {
            return "";
        }
        return value;
    }

    public static String coordinator(String room) {
        return "xennex-v3-" + room.toLowerCase(Locale.ROOT);
    }

    private static String extractRoomFromUrl(String urlText) {
        try {
            String query = new URI(urlText).getRawQuery();
            if (query == null) {
                return "";
            }
            for (String entry : query.split("&")) {
                String[] pair = entry.split("=", 2);
                if (pair.length == 2 && pair[0].equals("room")) {
                    return URLDecoder.decode(pair[1], "UTF-8");
                }
            }
            return "";
        } catch (Exception ignored) {
            return "";
        }
    }
}
