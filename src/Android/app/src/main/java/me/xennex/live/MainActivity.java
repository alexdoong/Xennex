package me.xennex.live;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Insets;
import android.media.projection.MediaProjectionManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputFilter;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.WebView;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

public final class MainActivity extends Activity {
    private static final int CAPTURE_REQUEST = 10;
    private static final int NOTIFICATION_REQUEST = 11;
    private static final String[] LICENSE_LABELS = {"WebRTC", "WebRTC SDK", "OkHttp / Okio / Kotlin"};
    private static final String[] LICENSE_FILES = {"WEBRTC.md", "WEBRTC-SDK.txt", "OKHTTP.txt"};

    private EditText room;
    private EditText name;
    private TextView status;
    private Button start;
    private String pendingRoom = "";
    private String pendingName = "";

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final Runnable refresh = new Runnable() {
        @Override
        public void run() {
            status.setText(CaptureService.status);
            start.setEnabled(!CaptureService.running);
            ui.postDelayed(this, 500);
        }
    };

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        ScrollView scroll = buildContentView();
        setContentView(scroll);

        if (state != null) {
            room.setText(state.getString("room", ""));
            name.setText(state.getString("name", ""));
            pendingRoom = state.getString("pendingRoom", "");
            pendingName = state.getString("pendingName", "");
        } else {
            prefill(getIntent());
        }

        requestNotificationPermissionIfNeeded();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (!CaptureService.running) {
            prefill(intent);
        }
    }

    private ScrollView buildContentView() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        int padding = (int) (20 * getResources().getDisplayMetrics().density);
        layout.setPadding(padding, padding, padding, padding);

        TextView title = new TextView(this);
        title.setText(R.string.app_title);
        title.setTextSize(24);
        layout.addView(title);

        TextView help = new TextView(this);
        help.setText(R.string.intro);
        layout.addView(help);

        room = new EditText(this);
        room.setHint(R.string.room_hint);
        room.setSingleLine(true);
        room.setFilters(new InputFilter[]{new InputFilter.LengthFilter(2048)});
        layout.addView(room);

        name = new EditText(this);
        name.setHint(R.string.name_hint);
        name.setSingleLine(true);
        name.setFilters(new InputFilter[]{new InputFilter.LengthFilter(40)});
        layout.addView(name);

        start = new Button(this);
        start.setText(R.string.start_capture);
        start.setOnClickListener(view -> requestCapture());
        layout.addView(start);

        Button stop = new Button(this);
        stop.setText(R.string.stop_capture);
        stop.setOnClickListener(view -> stopService(new Intent(this, CaptureService.class)));
        layout.addView(stop);

        status = new TextView(this);
        status.setTextIsSelectable(true);
        layout.addView(status);

        Button licenses = new Button(this);
        licenses.setText(R.string.licenses);
        licenses.setOnClickListener(view -> showLicensesDialog());
        layout.addView(licenses);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(layout);
        scroll.setOnApplyWindowInsetsListener((view, insets) -> {
            applySystemBarInsets(view, insets);
            return insets;
        });
        return scroll;
    }

    private static void applySystemBarInsets(View view, WindowInsets insets) {
        if (Build.VERSION.SDK_INT >= 30) {
            Insets bars = insets.getInsets(WindowInsets.Type.systemBars());
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            return;
        }
        applyLegacyInsets(view, insets);
    }

    @SuppressWarnings("deprecation")
    private static void applyLegacyInsets(View view, WindowInsets insets) {
        view.setPadding(
            insets.getSystemWindowInsetLeft(),
            insets.getSystemWindowInsetTop(),
            insets.getSystemWindowInsetRight(),
            insets.getSystemWindowInsetBottom()
        );
    }

    private void showLicensesDialog() {
        new AlertDialog.Builder(this)
            .setTitle(R.string.licenses)
            .setItems(LICENSE_LABELS, (dialog, which) -> showLicenseDocument(LICENSE_FILES[which]))
            .show();
    }

    private void showLicenseDocument(String fileName) {
        WebView page = new WebView(this);
        page.getSettings().setJavaScriptEnabled(false);
        page.getSettings().setBlockNetworkLoads(true);
        page.loadUrl("file:///android_asset/licenses/" + fileName);

        AlertDialog notice = new AlertDialog.Builder(this)
            .setView(page)
            .setPositiveButton(android.R.string.ok, null)
            .create();
        notice.setOnDismissListener(d -> page.destroy());
        notice.show();
    }

    private void requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT < 33) {
            return;
        }
        if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, NOTIFICATION_REQUEST);
        }
    }

    private void requestCapture() {
        if (CaptureService.running) {
            return;
        }
        pendingRoom = RoomAddress.normalize(room.getText().toString());
        pendingName = name.getText().toString().trim();
        if (pendingRoom.isEmpty()) {
            Toast.makeText(this, "Informe um código ou link válido.", Toast.LENGTH_LONG).show();
            return;
        }
        if (pendingName.isEmpty()) {
            pendingName = "Android";
        }
        pendingName = pendingName.substring(0, Math.min(40, pendingName.length()));

        MediaProjectionManager projection = getSystemService(MediaProjectionManager.class);
        startActivityForResult(projection.createScreenCaptureIntent(), CAPTURE_REQUEST);
    }

    @Override
    protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != CAPTURE_REQUEST) {
            return;
        }
        if (result != RESULT_OK || data == null || pendingRoom.isEmpty()) {
            CaptureService.status = getString(R.string.capture_cancelled);
            return;
        }
        Intent service = new Intent(this, CaptureService.class)
            .putExtra("projection", data)
            .putExtra("room", pendingRoom)
            .putExtra("name", pendingName);
        try {
            startForegroundService(service);
        } catch (RuntimeException error) {
            CaptureService.status = getString(R.string.start_failed);
        }
    }

    private void prefill(Intent intent) {
        Uri data = intent == null ? null : intent.getData();
        if (data == null || data.toString().length() > 2048) {
            return;
        }
        if (!"xennex-live".equals(data.getScheme()) || !"share".equals(data.getHost())) {
            return;
        }
        String code = RoomAddress.normalize(data.getQueryParameter("room"));
        if (code.isEmpty()) {
            return;
        }
        room.setText(code);
        String suggestedName = data.getQueryParameter("name");
        if (suggestedName != null) {
            name.setText(suggestedName.substring(0, Math.min(40, suggestedName.length())));
        }
        // Opening a link only fills fields. Capture always requires an explicit tap and system consent.
    }

    @Override
    protected void onSaveInstanceState(Bundle state) {
        state.putString("room", room.getText().toString());
        state.putString("name", name.getText().toString());
        state.putString("pendingRoom", pendingRoom);
        state.putString("pendingName", pendingName);
        super.onSaveInstanceState(state);
    }

    @Override
    protected void onResume() {
        super.onResume();
        ui.post(refresh);
    }

    @Override
    protected void onPause() {
        ui.removeCallbacks(refresh);
        super.onPause();
    }
}
