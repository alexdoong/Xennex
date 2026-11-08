package me.xennex.live;

import org.json.JSONException;
import org.json.JSONObject;

final class Json {
    private Json() {}

    static JSONObject object(Object... pairs) {
        JSONObject result = new JSONObject();
        try {
            for (int i = 0; i < pairs.length; i += 2) {
                result.put((String) pairs[i], pairs[i + 1]);
            }
        } catch (JSONException error) {
            throw new IllegalArgumentException(error);
        }
        return result;
    }
}
