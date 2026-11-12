package io.github.leejunhao791.sdktoolkit.javademo;

public final class JavaDeviceSdk {
    private JavaDeviceSdk() {}

    public static Reading read(int value) {
        return new Reading(value);
    }
}
