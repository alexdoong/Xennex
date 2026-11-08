package me.xennex.live;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

public class RoomRosterTest {
    private JSONObject fixture() {
        return Json.object(
            "type", "presence",
            "coordinator", "desktop",
            "participants", new JSONArray()
                .put(Json.object("peerId", "desktop", "name", "Viewer", "publications", new JSONArray()))
                .put(Json.object(
                    "peerId", "android",
                    "name", "Phone",
                    "publications", new JSONArray().put(
                        Json.object("id", "screen-1", "title", "Tela", "kind", "screen")
                    )
                ))
        );
    }

    @Test
    public void acceptsBrowserPresenceAndIgnoresOptionalExtensions() throws Exception {
        JSONObject value = fixture().put("extensions", new JSONArray().put("workspace-v1"));
        assertEquals(2, RoomRoster.parse(value, "android", "screen-1").size());
        assertTrue(RoomRoster.parse(value, "android", "screen-1").contains("desktop"));
    }

    @Test
    public void requiresOwnPublicationAndARealCoordinator() throws Exception {
        assertNull(RoomRoster.parse(fixture(), "android", "old-screen"));
        assertNull(RoomRoster.parse(fixture().put("coordinator", "stranger"), "android", "screen-1"));
        assertNull(RoomRoster.parse(fixture(), "stranger", "screen-1"));
    }

    @Test
    public void refusesDuplicateMembersPublicationsAndWrongTypes() throws Exception {
        JSONObject value = fixture();
        JSONArray people = value.getJSONArray("participants");
        people.put(people.getJSONObject(0));
        assertNull(RoomRoster.parse(value, "android", "screen-1"));

        value = fixture();
        people = value.getJSONArray("participants");
        people.getJSONObject(0).put("publications", people.getJSONObject(1).getJSONArray("publications"));
        assertNull(RoomRoster.parse(value, "android", "screen-1"));

        value = fixture();
        value.getJSONArray("participants").getJSONObject(0).put("name", 123);
        assertNull(RoomRoster.parse(value, "android", "screen-1"));
    }

    @Test
    public void refusesOversizedRosterAndDoesNotMutateAcceptedInput() throws Exception {
        JSONObject value = fixture();
        String original = value.toString();
        RoomRoster.parse(value, "android", "screen-1").clear();
        assertEquals(original, value.toString());

        JSONArray people = value.getJSONArray("participants");
        for (int i = 0; i < 32; i++) {
            people.put(Json.object("peerId", "p" + i, "name", "Viewer", "publications", new JSONArray()));
        }
        assertNull(RoomRoster.parse(value, "android", "screen-1"));
    }
}
