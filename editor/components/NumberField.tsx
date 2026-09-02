"use client";

import { NumberInput, NumberInputProps } from "@mantine/core";
import { useEffect, useRef, useState } from "react";

// Mantine has an `onValueChange` of its own with a different signature; it is
// dropped here so the name can mean the obvious thing.
type NumberFieldProps = Omit<
    NumberInputProps,
    "value" | "onChange" | "onValueChange"
> & {
    value: number;
    onValueChange: (value: number) => void;
    /** What the field falls back to when it is left empty. */
    fallback: number;
};

/**
 * A NumberInput you can actually clear.
 *
 * Feeding `Number(raw) || fallback` straight back into the value makes the
 * field snap to its default the moment you select everything and press
 * backspace, which is exactly when you were about to type a new number. This
 * keeps the half typed text as its own state and only publishes a number when
 * there is one, restoring the fallback on blur if the field was left empty.
 */
export const NumberField = ({
    value,
    onValueChange,
    fallback,
    ...props
}: NumberFieldProps) => {
    const [draft, setDraft] = useState<string | number>(value);
    const focused = useRef(false);

    // Follow the value when it changes from somewhere else (a loaded config, a
    // reset), but never fight the user while they are typing in this field.
    useEffect(() => {
        setDraft((current) =>
            (focused.current && current === "") || Number(current) === value
                ? current
                : value,
        );
    }, [value]);

    return (
        <NumberInput
            {...props}
            value={draft}
            onChange={(next) => {
                setDraft(next);
                if (next === "" || next === null) return;
                const parsed = Number(next);
                if (Number.isFinite(parsed)) onValueChange(parsed);
            }}
            onFocus={(event) => {
                focused.current = true;
                props.onFocus?.(event);
            }}
            onBlur={(event) => {
                focused.current = false;
                if (draft === "" || !Number.isFinite(Number(draft))) {
                    setDraft(fallback);
                    onValueChange(fallback);
                }
                props.onBlur?.(event);
            }}
        />
    );
};
