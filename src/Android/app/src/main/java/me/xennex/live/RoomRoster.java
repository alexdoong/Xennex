package me.xennex.live;

import java.util.HashSet;
import java.util.Set;
import org.json.JSONArray;
import org.json.JSONObject;

/** Validates the v3 presence contract before it can authorize a video recipient. */
final class RoomRoster {
    private static final int MAX_PARTICIPANTS = 32;
    private static final int MAX_PUBLICATIONS_PER_PERSON = 6;

    private RoomRoster() {}

    static Set<String> parse(JSONObject message, String self, String publication) {
        JSONArray people = message.optJSONArray("participants");
        if (people == null || people.length() > MAX_PARTICIPANTS) {
            return null;
        }
        Set<String> members = new HashSet<>();
        Set<String> publications = new HashSet<>();
        boolean ownPublicationFound = false;

        for (int i = 0; i < people.length(); i++) {
            JSONObject person = people.optJSONObject(i);
            if (!isValidPerson(person)) {
                return null;
            }
            String peerId = person.optString("peerId");
            if (!members.add(peerId)) {
                return null;
            }
            JSONArray pubs = person.optJSONArray("publications");
            if (pubs == null || pubs.length() > MAX_PUBLICATIONS_PER_PERSON) {
                return null;
            }
            for (int p = 0; p < pubs.length(); p++) {
                JSONObject pub = pubs.optJSONObject(p);
                if (!isValidPublication(pub, publications)) {
                    return null;
                }
                if (peerId.equals(self) && publication.equals(pub.optString("id"))) {
                    ownPublicationFound = true;
                }
            }
        }

        if (!ownPublicationFound) {
            return null;
        }
        if (!hasValidText(message, "coordinator", 100)) {
            return null;
        }
        if (!members.contains(message.optString("coordinator"))) {
            return null;
        }
        return members;
    }

    private static boolean isValidPerson(JSONObject person) {
        if (person == null) {
            return false;
        }
        return hasValidText(person, "peerId", 100) && hasValidText(person, "name", 40);
    }

    private static boolean isValidPublication(JSONObject pub, Set<String> seenIds) {
        if (pub == null) {
            return false;
        }
        if (!hasValidText(pub, "id", 80) || !hasValidText(pub, "title", 80)) {
            return false;
        }
        String kind = pub.optString("kind");
        if (!kind.equals("screen") && !kind.equals("camera")) {
            return false;
        }
        return seenIds.add(pub.optString("id"));
    }

    private static boolean hasValidText(JSONObject object, String field, int maxLength) {
        Object value = object.opt(field);
        if (!(value instanceof String)) {
            return false;
        }
        String text = (String) value;
        return !text.isEmpty() && text.length() <= maxLength;
    }
}
