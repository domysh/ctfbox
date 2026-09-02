/**
 * The shape of config.json, mirroring the `Config` / `Team` / `Node`
 * dataclasses of run.py. Keeping the key order identical keeps the diff clean
 * when the file is later rewritten by run.py or by the admin panel.
 */

export const ALL_ROLES = ["control", "vpn", "vm", "checker"] as const;
export type Role = (typeof ALL_ROLES)[number];

export type Team = {
    id: number;
    name: string;
    token: string;
    nop: boolean;
    image: string;
};

export type Node = {
    name: string;
    roles: string[];
    address: string;
    public_address: string;
    ssh: string;
    path: string;
    weight: number;
    checker_concurrency: number;
    teams: number[];
    vm_teams: number[];
};

export type VmMode = "incus" | "incus-vm" | "privileged" | "none";

export type Config = {
    gameserver_token: string;
    server_addr: string;
    wireguard_port: number;
    wireguard_profiles: number;
    dns: string;
    tick_time: number;
    flag_expire_ticks: number;
    initial_service_score: number;
    max_flags_per_request: number;
    submission_timeout: number | null;
    network_limit_bandwidth: string;
    max_vm_cpus: string;
    max_vm_mem: string;
    teams: Team[];
    vm_mode: VmMode;
    start_time: string | null;
    end_time: string | null;
    scoreboard_freeze_time: string | null;
    max_disk_size: string | null;
    gameserver_exposed_port: string | null;
    credential_server: string | null;
    debug: boolean;
    grace_time: number;
    checker_concurrency: number;
    checker_timeout: number;
    traffic_monitor: boolean;
    pcap: boolean;
    pcap_max_size: number;
    nodes: Node[];
};

/** A hex token of `bytes` bytes, the same shape run.py generates. */
export const randomToken = (bytes = 32): string => {
    const buffer = new Uint8Array(bytes);
    crypto.getRandomValues(buffer);
    return Array.from(buffer, (byte) => byte.toString(16).padStart(2, "0")).join(
        "",
    );
};

export const defaultConfig = (): Config => ({
    gameserver_token: randomToken(),
    server_addr: "",
    wireguard_port: 51000,
    wireguard_profiles: 10,
    dns: "1.1.1.1",
    tick_time: 120,
    flag_expire_ticks: 5,
    initial_service_score: 5000,
    max_flags_per_request: 3000,
    submission_timeout: 0.03,
    network_limit_bandwidth: "50mbit",
    max_vm_cpus: "1",
    max_vm_mem: "2G",
    teams: [],
    vm_mode: "incus",
    start_time: null,
    end_time: null,
    scoreboard_freeze_time: null,
    max_disk_size: "30G",
    gameserver_exposed_port: null,
    credential_server: null,
    debug: false,
    grace_time: 0,
    checker_concurrency: 0,
    checker_timeout: 30,
    traffic_monitor: true,
    pcap: false,
    pcap_max_size: 512,
    nodes: [],
});

export const defaultNode = (index: number): Node => ({
    name: index === 0 ? "control" : `node-${index}`,
    roles: index === 0 ? ["control", "vpn", "vm", "checker"] : ["vpn", "vm"],
    address: "",
    public_address: "",
    ssh: "",
    path: "~/ctfbox",
    weight: 1,
    checker_concurrency: 0,
    teams: [],
    vm_teams: [],
});

export const generateTeams = (count: number, withNop: boolean): Team[] => {
    const teams: Team[] = [];
    const total = count + (withNop ? 1 : 0);
    for (let i = 0; i < total; i++) {
        const nop = withNop && i === 0;
        teams.push({
            id: i,
            name: nop ? "Nop Team" : `Team ${i}`,
            token: randomToken(),
            nop,
            image: "",
        });
    }
    return teams;
};

const asNumber = (value: unknown, fallback: number): number => {
    const parsed = typeof value === "string" ? Number(value) : value;
    return typeof parsed === "number" && Number.isFinite(parsed)
        ? parsed
        : fallback;
};

const asString = (value: unknown, fallback: string): string =>
    typeof value === "string" ? value : fallback;

const asNullableString = (value: unknown): string | null =>
    typeof value === "string" && value.trim() !== "" ? value : null;

const asBool = (value: unknown, fallback: boolean): boolean =>
    typeof value === "boolean" ? value : fallback;

const asIntArray = (value: unknown): number[] =>
    Array.isArray(value)
        ? value
              .map((entry) => asNumber(entry, Number.NaN))
              .filter((entry) => Number.isFinite(entry))
        : [];

/**
 * Reads an arbitrary object into a Config, filling in whatever is missing.
 * Configurations written before a field existed must keep importing cleanly.
 */
/** Whether a node terminates tunnels, and so has a public address at all. */
export const isVpnNode = (roles: string[]) =>
    roles.includes("vpn") || roles.includes("router");

/**
 * The fields to drop when a node's roles change.
 *
 * A field the editor stops showing must stop being written too, otherwise the
 * exported config carries a value nobody can see any more: give a node the vpn
 * role, type a public address, take the role away, and that address is still
 * in the JSON with no field left to correct it.
 */
export const rolesPatch = (node: Node, roles: string[]): Partial<Node> => {
    const patch: Partial<Node> = { roles };
    if (!isVpnNode(roles) && node.public_address) patch.public_address = "";
    if (!roles.includes("checker") && node.checker_concurrency)
        patch.checker_concurrency = 0;
    return patch;
};

export const parseConfig = (raw: unknown): Config => {
    const base = defaultConfig();
    if (typeof raw !== "object" || raw === null) return base;
    const data = raw as Record<string, unknown>;

    const teams: Team[] = Array.isArray(data.teams)
        ? data.teams.map((entry, index) => {
              const team = (entry ?? {}) as Record<string, unknown>;
              return {
                  id: asNumber(team.id, index),
                  name: asString(team.name, `Team ${index}`),
                  token: asString(team.token, randomToken()),
                  nop: asBool(team.nop, false),
                  image: asString(team.image, ""),
              };
          })
        : [];

    const parsedNodes: Node[] = Array.isArray(data.nodes)
        ? data.nodes.map((entry, index) => {
              const node = (entry ?? {}) as Record<string, unknown>;
              const address = asString(node.address, "");
              return {
                  name: asString(node.name, `node-${index}`),
                  roles: Array.isArray(node.roles)
                      ? node.roles.map((role) => String(role))
                      : [...ALL_ROLES],
                  address,
                  public_address: asString(node.public_address, address),
                  ssh: asString(node.ssh, ""),
                  path: asString(node.path, "~/ctfbox"),
                  weight: asNumber(node.weight, 1),
                  checker_concurrency: asNumber(node.checker_concurrency, 0),
                  teams: asIntArray(node.teams),
                  vm_teams: asIntArray(node.vm_teams),
              };
          })
        : [];

    // The control role belongs to the first node and only to it: exactly one
    // machine owns the game server and the database, and run.py resolves it the
    // same way. A config that says otherwise is corrected rather than refused.
    const nodes: Node[] = parsedNodes.map((node, index) => ({
        ...node,
        roles:
            index === 0
                ? ["control", ...node.roles.filter((role) => role !== "control")]
                : node.roles.filter((role) => role !== "control"),
    }));

    const vmMode = asString(data["vm_mode"], base.vm_mode);

    return {
        gameserver_token: asString(data.gameserver_token, base.gameserver_token),
        server_addr: asString(data.server_addr, ""),
        wireguard_port: asNumber(data.wireguard_port, base.wireguard_port),
        wireguard_profiles: asNumber(
            data.wireguard_profiles,
            base.wireguard_profiles,
        ),
        dns: asString(data.dns, base.dns),
        tick_time: asNumber(data.tick_time, base.tick_time),
        flag_expire_ticks: asNumber(
            data.flag_expire_ticks,
            base.flag_expire_ticks,
        ),
        initial_service_score: asNumber(
            data.initial_service_score,
            base.initial_service_score,
        ),
        max_flags_per_request: asNumber(
            data.max_flags_per_request,
            base.max_flags_per_request,
        ),
        submission_timeout:
            data.submission_timeout === null
                ? null
                : asNumber(data.submission_timeout, base.submission_timeout ?? 0),
        network_limit_bandwidth: asString(
            data.network_limit_bandwidth,
            base.network_limit_bandwidth,
        ),
        max_vm_cpus: String(data.max_vm_cpus ?? base.max_vm_cpus),
        max_vm_mem: asString(data.max_vm_mem, base.max_vm_mem),
        teams,
        vm_mode: (["incus", "incus-vm", "privileged", "none"].includes(vmMode)
            ? vmMode
            : base.vm_mode) as VmMode,
        start_time: asNullableString(data.start_time),
        end_time: asNullableString(data.end_time),
        scoreboard_freeze_time: asNullableString(data.scoreboard_freeze_time),
        max_disk_size: asNullableString(data.max_disk_size),
        gameserver_exposed_port: asNullableString(data.gameserver_exposed_port),
        credential_server: asNullableString(data.credential_server),
        debug: asBool(data.debug, false),
        grace_time: asNumber(data.grace_time, base.grace_time),
        checker_concurrency: asNumber(
            data.checker_concurrency,
            base.checker_concurrency,
        ),
        checker_timeout: asNumber(data.checker_timeout, base.checker_timeout),
        traffic_monitor: asBool(data.traffic_monitor, true),
        pcap: asBool(data.pcap, false),
        pcap_max_size: asNumber(data.pcap_max_size, base.pcap_max_size),
        nodes,
    };
};

/**
 * Produces the object actually written to config.json. Optional sections are
 * dropped when they carry no information, so a single machine setup stays as
 * short as it has always been.
 */
export const serializeConfig = (config: Config): Record<string, unknown> => {
    const out: Record<string, unknown> = {
        gameserver_token: config.gameserver_token,
        server_addr: config.server_addr,
        wireguard_port: config.wireguard_port,
        wireguard_profiles: config.wireguard_profiles,
        dns: config.dns,
        tick_time: config.tick_time,
        flag_expire_ticks: config.flag_expire_ticks,
        initial_service_score: config.initial_service_score,
        max_flags_per_request: config.max_flags_per_request,
        submission_timeout: config.submission_timeout,
        network_limit_bandwidth: config.network_limit_bandwidth,
        max_vm_cpus: config.max_vm_cpus,
        max_vm_mem: config.max_vm_mem,
        teams: config.teams.map((team) => ({
            id: team.id,
            name: team.name,
            token: team.token,
            nop: team.nop,
            image: team.image,
        })),
        vm_mode: config.vm_mode,
        start_time: config.start_time,
        end_time: config.end_time,
        scoreboard_freeze_time: config.scoreboard_freeze_time,
        max_disk_size: config.vm_mode === "none" ? null : config.max_disk_size,
        gameserver_exposed_port: config.gameserver_exposed_port,
        credential_server: config.credential_server,
        debug: config.debug,
        grace_time: config.grace_time,
        checker_concurrency: config.checker_concurrency,
        checker_timeout: config.checker_timeout,
        traffic_monitor: config.traffic_monitor,
    };

    if (config.nodes.length > 0) {
        out.nodes = config.nodes.map((node) => {
            const entry: Record<string, unknown> = {
                name: node.name,
                roles: node.roles,
                address: node.address,
            };
            if (node.public_address && node.public_address !== node.address)
                entry.public_address = node.public_address;
            if (node.ssh) entry.ssh = node.ssh;
            if (node.path && node.path !== "~/ctfbox") entry.path = node.path;
            if (node.weight !== 1) entry.weight = node.weight;
            if (node.checker_concurrency > 0)
                entry.checker_concurrency = node.checker_concurrency;
            if (node.teams.length > 0) entry.teams = node.teams;
            if (node.vm_teams.length > 0) entry.vm_teams = node.vm_teams;
            return entry;
        });
    }
    return out;
};

export const configToJson = (config: Config): string =>
    JSON.stringify(serializeConfig(config), null, 4);
