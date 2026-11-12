package io.github.leejunhao791.sdktoolkit.consumer;

import android.app.Activity;
import android.app.Instrumentation;
import android.os.Bundle;
import android.os.Process;

public final class JniSmokeRunner extends Instrumentation {
    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override
    public void onStart() {
        int actual = Smoke.callSdk(42);
        Bundle results = new Bundle();
        results.putInt("jni_result", actual);
        results.putBoolean("process_64_bit", Process.is64Bit());
        finish(actual == 42 ? Activity.RESULT_OK : Activity.RESULT_CANCELED, results);
    }
}
