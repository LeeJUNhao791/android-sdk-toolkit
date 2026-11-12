package io.github.leejunhao791.sdktoolkit;

public final class DeviceSdk {
    static {
        System.loadLibrary("device");
    }

    private DeviceSdk() {}

    public static native int roundTrip(int value);
}
