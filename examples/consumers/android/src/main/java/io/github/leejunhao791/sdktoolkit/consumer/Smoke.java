package io.github.leejunhao791.sdktoolkit.consumer;

import io.github.leejunhao791.sdktoolkit.DeviceSdk;

public final class Smoke {
    private Smoke() {}

    public static int callSdk(int value) {
        return DeviceSdk.roundTrip(value);
    }
}
