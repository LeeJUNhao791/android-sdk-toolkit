package io.github.leejunhao791.sdktoolkit.demo;

import android.app.Activity;
import android.os.Bundle;
import android.util.Log;
import android.widget.TextView;
import io.github.leejunhao791.sdktoolkit.DeviceSdk;

public final class MainActivity extends Activity {
    private static final String TAG = "SdkToolkitDemo";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        String mode = getIntent().getStringExtra("scenario");
        String message;
        try {
            if ("missing".equals(mode)) {
                System.loadLibrary("device_missing");
            }
            int value = DeviceSdk.roundTrip(42);
            if ("binding".equals(mode)) {
                missingNative();
            }
            message = "roundTrip returned " + value;
            Log.i(TAG, message);
        } catch (UnsatisfiedLinkError error) {
            message = "scenario=" + mode + " " + error;
            Log.e(TAG, "scenario=" + mode, error);
        }
        TextView text = new TextView(this);
        text.setText(message);
        setContentView(text);
    }

    private static native void missingNative();
}
