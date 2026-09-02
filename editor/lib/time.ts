/** Helpers to move between the `datetime-local` inputs and RFC 3339. */

export const toLocalInput = (value: string | null): string => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

export const fromLocalInput = (value: string): string | null => {
    if (!value) return null;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    return date.toISOString();
};

export const humanDuration = (seconds: number): string => {
    if (!Number.isFinite(seconds) || seconds <= 0) return "disabled";
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const rest = seconds % 60;
    return [
        hours ? `${hours}h` : "",
        minutes ? `${minutes}m` : "",
        rest ? `${rest}s` : "",
    ]
        .filter(Boolean)
        .join(" ");
};
