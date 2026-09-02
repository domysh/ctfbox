import pako from "pako";
import { Config, configToJson, parseConfig } from "./config";

/**
 * `run.py` accepts the configuration pasted as zlib-deflated base64, which is
 * what makes the "copy compressed" button worth existing: a full config with a
 * few dozen teams is a lot to paste by hand.
 */
export const compressConfig = (config: Config): string => {
    const deflated = pako.deflate(configToJson(config));
    let binary = "";
    for (const byte of deflated) binary += String.fromCharCode(byte);
    return btoa(binary);
};

export class ImportError extends Error {}

/** Accepts either raw JSON or the compressed base64 form. */
export const importConfig = (input: string): Config => {
    const text = input.trim();
    if (!text) throw new ImportError("Nothing to import.");

    if (text.startsWith("{")) {
        try {
            return parseConfig(JSON.parse(text));
        } catch (error) {
            throw new ImportError(
                `That does not look like valid JSON: ${(error as Error).message}`,
            );
        }
    }

    try {
        const binary = atob(text.replace(/\s/g, ""));
        const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
        const json = pako.inflate(bytes, { to: "string" });
        return parseConfig(JSON.parse(json));
    } catch {
        // Older exports were plain base64 without the deflate step.
        try {
            return parseConfig(JSON.parse(atob(text.replace(/\s/g, ""))));
        } catch {
            throw new ImportError(
                "Could not read the configuration: paste the JSON or the compressed string produced by this editor.",
            );
        }
    }
};

export const downloadConfig = (config: Config) => {
    const blob = new Blob([configToJson(config)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "config.json";
    anchor.click();
    URL.revokeObjectURL(url);
};
