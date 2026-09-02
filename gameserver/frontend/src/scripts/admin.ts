import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

const baseUrl = import.meta.env.DEV ? "http://127.0.0.1:8888" : "";

/*
 * There is no login here on purpose. The control room is reachable only from an
 * admin WireGuard profile (10.80.253.0/24 by default): the game server decides
 * from the source address of the request, so the browser has nothing to store
 * and nothing to leak.
 */

export class AdminForbiddenError extends Error {}

export type AdminAccess = {
    admin: boolean;
    ip: string;
    /** Only the published demo sets this: there is no game behind it, so the
     *  panel shows itself read only instead of failing on every button. */
    demo?: boolean;
};

/** Set from the whoami answer, read by adminFetch before it changes anything. */
let readOnlyDemo = false;

export const isReadOnlyDemo = () => readOnlyDemo;

async function adminFetch<T>(
    path: string,
    options: RequestInit = {},
): Promise<T> {
    if (readOnlyDemo && options.method && options.method !== "GET") {
        throw new Error(
            "This is a read-only demo: run CTFBox to change anything.",
        );
    }
    const response = await fetch(baseUrl + "/api/admin" + path, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(options.headers ?? {}),
        },
    });
    if (response.status === 403 || response.status === 401) {
        throw new AdminForbiddenError(
            "This page is only available through an admin VPN profile.",
        );
    }
    if (!response.ok) {
        throw new Error((await response.text()) || response.statusText);
    }
    const text = await response.text();
    return (text ? JSON.parse(text) : null) as T;
}

export const adminGet = <T,>(path: string) => adminFetch<T>(path);
export const adminSend = <T,>(path: string, method: string, body?: unknown) =>
    adminFetch<T>(path, {
        method,
        body: body === undefined ? undefined : JSON.stringify(body),
    });

/** Whether the browser is currently talking through an admin profile. */
export const useAdminAccess = () =>
    useQuery({
        queryKey: ["admin-access"],
        queryFn: async () => {
            const access = await adminGet<AdminAccess>("/whoami");
            readOnlyDemo = access.demo === true;
            return access;
        },
        refetchInterval: 60 * 1000,
        staleTime: 30 * 1000,
        retry: false,
    });

// ---------------------------------------------------------------------------
// types
// ---------------------------------------------------------------------------

export type AdminSettings = {
    tick_time: number;
    flag_expire_ticks: number;
    initial_service_score: number;
    max_flags_per_request: number;
    submission_timeout: number | null;
    grace_time: number;
    checker_timeout: number;
    flag_regex: string;
    start_time: string | null;
    end_time: string | null;
    scoreboard_freeze_time: string | null;
    scoreboard_frozen: boolean;
    scoreboard_freeze_round: number;
    game_paused: boolean;
};

export type AdminNode = {
    name: string;
    roles: string[];
    address: string;
    network_state: string;
    banned_teams: number[] | null;
    version: string;
    first_seen: string;
    last_seen: string;
    alive: boolean;
    seen: boolean;
};

export type AdminWorker = {
    id: string;
    name: string;
    address: string;
    capacity: number;
    embedded: boolean;
    version: string;
    running: number;
    completed: number;
    failed: number;
    last_seen: string;
    alive: boolean;
};

export type AdminOverview = {
    round: number;
    settings: AdminSettings;
    network_state: string;
    node: string;
    nodes: AdminNode[];
    workers: AdminWorker[];
    queue: { pending: number; running: number; last_job_id: number };
    capacity: number;
    teams: number;
    services: number;
    next_round_at: string;
    server_time: string;
};

export type AdminTeam = {
    id: number;
    name: string;
    image: string;
    nop: boolean;
    game_banned: boolean;
    network_banned: boolean;
    ban_reason: string;
    node: string;
    ip: string;
    token: string;
};

export type AdminService = {
    name: string;
    enabled: boolean;
    weight: number;
    description: string;
    present: boolean;
};

export type AdminJob = {
    id: number;
    round: number;
    team_id: number;
    team: string;
    service: string;
    action: string;
    state: string;
    worker: string;
    status: number;
    message: string;
    created_at: string;
    started_at: string | null;
    finished_at: string | null;
    duration_ms: number;
};

export type AttackEdge = {
    from_team: number;
    to_team: number;
    service: string;
    flags: number;
    points: number;
};

export type TrafficPoint = {
    at: string;
    team: number;
    kind: string;
    bytes: number;
    packets: number;
    conns: number;
};

export type TrafficEdge = {
    src_team: number;
    dst_team: number;
    bytes: number;
    packets: number;
    conns: number;
    kind: string;
};

export type SubmissionEvent = {
    id: number;
    at: string;
    round: number;
    team_id: number;
    team: string;
    victim_id: number;
    victim: string;
    service: string;
    flag: string;
    status: string;
    reason: string;
    points: number;
};

export type SubmissionStats = {
    reasons: { reason: string; count: number }[];
    teams: {
        team_id: number;
        total: number;
        accepted: number;
        points: number;
    }[];
    rounds: { round: number; total: number; accepted: number }[];
};

export type PeerProfile = {
    team_id: number;
    profile: number;
    address: string;
    node: string;
    rx: number;
    tx: number;
    handshake: number;
};

export type PeerTeamTotals = {
    team_id: number;
    rx: number;
    tx: number;
    profiles: number;
    active: number;
};

export type PcapNodeStatus = {
    node: string;
    enabled: boolean;
    interface: string;
    files: number;
    bytes: number;
    max_bytes: number;
    rotate_seconds: number;
    oldest: number | null;
    newest: number | null;
    free_bytes: number | null;
    error?: string;
};

export type AuditEntry = {
    id: number;
    at: string;
    actor: string;
    action: string;
    target: string;
    details: string;
};

export type Announcement = {
    id: number;
    at: string;
    title: string;
    body: string;
    severity: string;
    visible: boolean;
    author: string;
};

// ---------------------------------------------------------------------------
// hooks
// ---------------------------------------------------------------------------

export const useAdminOverview = () =>
    useQuery({
        queryKey: ["admin", "overview"],
        queryFn: () => adminGet<AdminOverview>("/overview"),
        refetchInterval: 5000,
    });

export const useAdminTeams = () =>
    useQuery({
        queryKey: ["admin", "teams"],
        queryFn: () => adminGet<AdminTeam[]>("/teams"),
    });

export const useAdminServices = () =>
    useQuery({
        queryKey: ["admin", "services"],
        queryFn: () => adminGet<AdminService[]>("/services"),
    });

export const useAdminJobs = (filters: Record<string, string> = {}) => {
    const params = new URLSearchParams(
        Object.entries(filters).filter(([, value]) => value !== ""),
    ).toString();
    return useQuery({
        queryKey: ["admin", "jobs", params],
        queryFn: () => adminGet<AdminJob[]>(`/jobs${params ? "?" + params : ""}`),
        refetchInterval: 5000,
    });
};

export const useAttackGraph = (sinceRound?: number) =>
    useQuery({
        queryKey: ["admin", "attack-graph", sinceRound ?? "all"],
        queryFn: () =>
            adminGet<AttackEdge[]>(
                `/attack-graph${sinceRound != null ? `?since_round=${sinceRound}` : ""}`,
            ),
        refetchInterval: 15000,
    });

export const useTraffic = (minutes: number) =>
    useQuery({
        queryKey: ["admin", "traffic", minutes],
        queryFn: () =>
            adminGet<{
                minutes: number;
                bucket_seconds: number;
                points: TrafficPoint[];
            }>(`/traffic?minutes=${minutes}`),
        refetchInterval: 15000,
    });

export const useTrafficMatrix = (minutes: number) =>
    useQuery({
        queryKey: ["admin", "traffic-matrix", minutes],
        queryFn: () =>
            adminGet<{ minutes: number; edges: TrafficEdge[] }>(
                `/traffic/matrix?minutes=${minutes}`,
            ),
        refetchInterval: 15000,
    });

export const useSubmissions = (filters: Record<string, string> = {}) => {
    const params = new URLSearchParams(
        Object.entries(filters).filter(([, value]) => value !== ""),
    ).toString();
    return useQuery({
        queryKey: ["admin", "submissions", params],
        queryFn: () =>
            adminGet<{
                total: number;
                limit: number;
                events: SubmissionEvent[];
            }>(`/submissions${params ? "?" + params : ""}`),
        refetchInterval: 10000,
    });
};

export const useSubmissionStats = (filters: Record<string, string> = {}) => {
    const params = new URLSearchParams(
        Object.entries(filters).filter(([, value]) => value !== ""),
    ).toString();
    return useQuery({
        queryKey: ["admin", "submission-stats", params],
        queryFn: () =>
            adminGet<SubmissionStats>(
                `/submissions/stats${params ? "?" + params : ""}`,
            ),
        refetchInterval: 10000,
    });
};

export const usePeerTraffic = (minutes: number) =>
    useQuery({
        queryKey: ["admin", "peer-traffic", minutes],
        queryFn: () =>
            adminGet<{
                minutes: number;
                profiles: PeerProfile[];
                teams: PeerTeamTotals[];
                suspended: string[];
            }>(`/traffic/peers?minutes=${minutes}`),
        refetchInterval: 15000,
    });

export const suspendProfile = (address: string, suspended: boolean) =>
    adminSend(`/vpn/profiles/${address}/suspend`, "POST", { suspended });

export const usePcapStatus = () =>
    useQuery({
        queryKey: ["admin", "pcap"],
        queryFn: () =>
            adminGet<{
                enabled: boolean;
                bytes: number;
                nodes: PcapNodeStatus[];
            }>("/pcap/status"),
        refetchInterval: 20000,
    });

/** The capture is a file download, so it goes through the browser rather than
 *  through fetch: the admin gate is the source address, not a header. */
export const pcapDownloadUrl = (filters: Record<string, string>) => {
    const params = new URLSearchParams(
        Object.entries(filters).filter(([, value]) => value !== ""),
    ).toString();
    return `${baseUrl}/api/admin/pcap/download${params ? "?" + params : ""}`;
};

export const useAuditLog = () =>
    useQuery({
        queryKey: ["admin", "audit"],
        queryFn: () => adminGet<AuditEntry[]>("/audit"),
        refetchInterval: 10000,
    });

export const useAdminAnnouncements = () =>
    useQuery({
        queryKey: ["announcements"],
        queryFn: async () =>
            (await fetch(baseUrl + "/api/announcements").then((r) =>
                r.json(),
            )) as Announcement[],
        refetchInterval: 15000,
    });

/** Invalidates everything the admin panel shows after a mutation. */
export const useAdminMutation = <TVars,>(
    fn: (vars: TVars) => Promise<unknown>,
    keys: string[] = ["admin"],
) => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: fn,
        onSuccess: () => {
            for (const key of keys)
                queryClient.invalidateQueries({ queryKey: [key] });
        },
    });
};

export const formatBytes = (bytes: number) => {
    const units = ["B", "KB", "MB", "GB", "TB"];
    let value = bytes;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
        value /= 1024;
        unit++;
    }
    return `${value.toFixed(value < 10 && unit > 0 ? 1 : 0)} ${units[unit]}`;
};

export const toLocalInput = (value: string | null) => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

export const fromLocalInput = (value: string) =>
    value ? new Date(value).toISOString() : null;
