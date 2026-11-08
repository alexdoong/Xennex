package me.xennex.live;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Insets;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.projection.MediaProjectionManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputFilter;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

public final class MainActivity extends Activity {
    private static final int CAPTURE_REQUEST = 10;
    private static final int NOTIFICATION_REQUEST = 11;
    private static final String LIVE_BASE_URL = "https://xennex-live.alexdoong11.workers.dev/";
    private static final String[] LICENSE_LABELS = {"WebRTC", "WebRTC SDK", "OkHttp / Okio / Kotlin"};
    private static final String[] LICENSE_FILES = {"WEBRTC.md", "WEBRTC-SDK.txt", "OKHTTP.txt"};

    private EditText room;
    private EditText name;
    private TextView status;
    private Button start;
    private Button stop;
    private LinearLayout formDrawer;
    private WebView roomWebView;
    private String pendingRoom = "";
    private String pendingName = "";

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final Runnable refresh = new Runnable() {
        @Override
        public void run() {
            status.setText(CaptureService.status);
            start.setEnabled(!CaptureService.running);
            stop.setVisibility(CaptureService.running ? View.VISIBLE : View.GONE);
            ui.postDelayed(this, 500);
        }
    };

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().getDecorView().setBackgroundColor(Color.parseColor("#0C0814"));
        LinearLayout root = buildContentView();
        setContentView(root);

        if (state != null) {
            room.setText(state.getString("room", ""));
            name.setText(state.getString("name", ""));
            pendingRoom = state.getString("pendingRoom", "");
            pendingName = state.getString("pendingName", "");
        } else {
            prefill(getIntent());
        }

        loadInitialRoomPage();
        requestNotificationPermissionIfNeeded();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (!CaptureService.running) {
            prefill(intent);
            loadInitialRoomPage();
        }
    }

    private LinearLayout buildContentView() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.parseColor("#0C0814"));

        root.addView(buildTopControlBar(), new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ));

        formDrawer = buildManualDrawer();
        root.addView(formDrawer, new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ));

        roomWebView = buildRoomWebView();
        LinearLayout.LayoutParams webParams = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            0,
            1f
        );
        root.addView(roomWebView, webParams);

        root.setOnApplyWindowInsetsListener((view, insets) -> {
            applySystemBarInsets(view, insets);
            return insets;
        });
        return root;
    }

    private LinearLayout buildTopControlBar() {
        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.VERTICAL);
        bar.setBackgroundColor(Color.parseColor("#140E24"));
        int padH = dp(14);
        int padV = dp(10);
        bar.setPadding(padH, padV, padH, padV);

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);

        TextView title = new TextView(this);
        title.setText(R.string.app_title);
        title.setTextColor(Color.parseColor("#F3ECFF"));
        title.setTextSize(16);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        row.addView(title, titleParams);

        Button toggleDrawer = createPillButton("Sala", "#23193D", "#DAC8FF");
        toggleDrawer.setOnClickListener(v -> {
            boolean visible = formDrawer.getVisibility() == View.VISIBLE;
            formDrawer.setVisibility(visible ? View.GONE : View.VISIBLE);
        });
        row.addView(toggleDrawer, marginEnd(dp(6)));

        start = createPillButton(getString(R.string.start_capture), "#8B5CF6", "#FFFFFF");
        start.setOnClickListener(view -> syncFromWebViewAndRequestCapture());
        row.addView(start, marginEnd(dp(6)));

        stop = createPillButton(getString(R.string.stop_capture), "#DC2626", "#FFFFFF");
        stop.setVisibility(View.GONE);
        stop.setOnClickListener(view -> stopService(new Intent(this, CaptureService.class)));
        row.addView(stop);

        bar.addView(row);

        status = new TextView(this);
        status.setTextColor(Color.parseColor("#B9A6DC"));
        status.setTextSize(12);
        status.setPadding(0, dp(4), 0, 0);
        status.setTextIsSelectable(true);
        bar.addView(status);

        return bar;
    }

    private LinearLayout buildManualDrawer() {
        LinearLayout drawer = new LinearLayout(this);
        drawer.setOrientation(LinearLayout.VERTICAL);
        drawer.setBackgroundColor(Color.parseColor("#1A1230"));
        int pad = dp(12);
        drawer.setPadding(pad, pad, pad, pad);
        drawer.setVisibility(View.GONE);

        TextView help = new TextView(this);
        help.setText(R.string.intro);
        help.setTextColor(Color.parseColor("#CDBCEB"));
        help.setTextSize(12);
        drawer.addView(help);

        room = createStyledInput(R.string.room_hint, 2048);
        drawer.addView(room, topMargin(dp(8)));

        name = createStyledInput(R.string.name_hint, 40);
        drawer.addView(name, topMargin(dp(8)));

        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.setGravity(Gravity.END);

        Button openRoom = createPillButton("Abrir sala na tela", "#2B1E4A", "#EFE7FF");
        openRoom.setOnClickListener(v -> {
            String normalized = RoomAddress.normalize(room.getText().toString());
            if (!normalized.isEmpty()) {
                roomWebView.loadUrl(LIVE_BASE_URL + "?room=" + Uri.encode(normalized));
                drawer.setVisibility(View.GONE);
            }
        });
        actions.addView(openRoom, marginEnd(dp(8)));

        Button licenses = createPillButton(getString(R.string.licenses), "#23193D", "#B9A6DC");
        licenses.setOnClickListener(view -> showLicensesDialog());
        actions.addView(licenses);

        drawer.addView(actions, topMargin(dp(8)));
        return drawer;
    }

    @SuppressLint("SetJavaScriptEnabled")
    private WebView buildRoomWebView() {
        WebView web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#0C0814"));
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setDatabaseEnabled(true);

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                request.grant(request.getResources());
            }
        });

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (uri != null && "xennex-live".equals(uri.getScheme())) {
                    handleDeepLinkUri(uri);
                    requestCapture();
                    return true;
                }
                return false;
            }
        });
        return web;
    }

    private void loadInitialRoomPage() {
        if (roomWebView == null) {
            return;
        }
        String currentRoom = RoomAddress.normalize(room.getText().toString());
        String targetUrl = currentRoom.isEmpty()
            ? LIVE_BASE_URL
            : LIVE_BASE_URL + "?room=" + Uri.encode(currentRoom);
        roomWebView.loadUrl(targetUrl);
    }

    private void syncFromWebViewAndRequestCapture() {
        if (roomWebView == null) {
            requestCapture();
            return;
        }
        String script = "(function(){"
            + "var params = new URLSearchParams(location.search);"
            + "var r = params.get('room') || (document.querySelector('.room-toolbar strong') && document.querySelector('.room-toolbar strong').textContent) || (document.querySelector('.room-entry input') && document.querySelectorAll('.room-entry input')[1] && document.querySelectorAll('.room-entry input')[1].value) || '';"
            + "var n = localStorage.getItem('xennex_display_name') || (document.querySelector('.room-entry input') && document.querySelector('.room-entry input').value) || '';"
            + "return JSON.stringify({room: r, name: n});"
            + "})()";
        roomWebView.evaluateJavascript(script, value -> {
            applyWebViewRoomAndName(value);
            requestCapture();
        });
    }

    private void applyWebViewRoomAndName(String rawJson) {
        if (rawJson == null || rawJson.length() < 4) {
            return;
        }
        try {
            org.json.JSONTokener tokener = new org.json.JSONTokener(rawJson);
            Object parsed = tokener.nextValue();
            if (parsed instanceof String) {
                parsed = new org.json.JSONObject((String) parsed);
            }
            if (!(parsed instanceof org.json.JSONObject)) {
                return;
            }
            org.json.JSONObject obj = (org.json.JSONObject) parsed;
            String webRoom = RoomAddress.normalize(obj.optString("room", ""));
            String webName = obj.optString("name", "").trim();
            if (!webRoom.isEmpty()) {
                room.setText(webRoom);
            }
            if (!webName.isEmpty() && name.getText().toString().trim().isEmpty()) {
                name.setText(webName.substring(0, Math.min(40, webName.length())));
            }
        } catch (org.json.JSONException ignored) {
            // Keep existing manual fields when WebView state is unavailable.
        }
    }

    private EditText createStyledInput(int hintRes, int maxLength) {
        EditText input = new EditText(this);
        input.setHint(hintRes);
        input.setHintTextColor(Color.parseColor("#8875AD"));
        input.setTextColor(Color.parseColor("#F3ECFF"));
        input.setSingleLine(true);
        input.setTextSize(14);
        input.setFilters(new InputFilter[]{new InputFilter.LengthFilter(maxLength)});
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(Color.parseColor("#110B1F"));
        bg.setCornerRadius(dp(10));
        bg.setStroke(dp(1), Color.parseColor("#352459"));
        input.setBackground(bg);
        int padH = dp(12);
        int padV = dp(8);
        input.setPadding(padH, padV, padH, padV);
        return input;
    }

    private Button createPillButton(String text, String bgHex, String fgHex) {
        Button button = new Button(this);
        button.setText(text);
        button.setAllCaps(false);
        button.setTextColor(Color.parseColor(fgHex));
        button.setTextSize(13);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(Color.parseColor(bgHex));
        bg.setCornerRadius(dp(18));
        button.setBackground(bg);
        button.setMinimumHeight(dp(36));
        button.setMinHeight(dp(36));
        button.setPadding(dp(14), dp(6), dp(14), dp(6));
        return button;
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density);
    }

    private static LinearLayout.LayoutParams marginEnd(int px) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        );
        params.setMarginEnd(px);
        return params;
    }

    private static LinearLayout.LayoutParams topMargin(int px) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        );
        params.topMargin = px;
        return params;
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
            formDrawer.setVisibility(View.VISIBLE);
            Toast.makeText(this, "Entre em uma sala abaixo ou digite o código da sala.", Toast.LENGTH_LONG).show();
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
        handleDeepLinkUri(data);
    }

    private void handleDeepLinkUri(Uri data) {
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

    @Override
    protected void onDestroy() {
        if (roomWebView != null) {
            roomWebView.destroy();
            roomWebView = null;
        }
        super.onDestroy();
    }
}
