/**
 * Cross checks the editor against run.py: the JSON it produces must be
 * something run.py can load, and the team distribution it previews must be the
 * one run.py computes.
 */
import { describe, expect, test } from "bun:test";
import {
    Config,
    configToJson,
    defaultConfig,
    defaultNode,
    generateTeams,
    parseConfig,
    rolesPatch,
    serializeConfig,
} from "../lib/config";
import { assignTeams, effectiveNodes, validateTopology } from "../lib/topology";
import { compressConfig, importConfig } from "../lib/transfer";

const sample = (): Config => ({
    ...defaultConfig(),
    server_addr: "ctf.example.com",
    teams: generateTeams(6, true),
});

describe("config", () => {
    test("round trips through JSON", () => {
        const config = sample();
        const back = parseConfig(JSON.parse(configToJson(config)));
        expect(back).toEqual(config);
    });

    test("round trips through the compressed form", () => {
        const config = sample();
        expect(importConfig(compressConfig(config))).toEqual(config);
    });

    test("imports a config written before the new fields existed", () => {
        const legacy = {
            gameserver_token: "tok",
            server_addr: "1.2.3.4",
            wireguard_port: 51000,
            teams: [{ id: 0, name: "Nop", token: "a", nop: true, image: "" }],
            vm_mode: "incus",
        };
        const config = parseConfig(legacy);
        expect(config.gameserver_token).toBe("tok");
        expect(config.scoreboard_freeze_time).toBeNull();
        expect(config.traffic_monitor).toBe(true);
        expect(config.checker_timeout).toBe(30);
        expect(config.nodes).toEqual([]);
        expect(config.teams).toHaveLength(1);
    });

    test("omits the nodes section on a single machine setup", () => {
        expect(serializeConfig(sample())).not.toHaveProperty("nodes");
    });

    test("never writes an admin allow list: the VPN profile is the credential", () => {
        expect(serializeConfig(sample())).not.toHaveProperty("admin_networks");
        expect(serializeConfig(sample())).not.toHaveProperty("admin_token");
    });

    test("keeps the incus-vm mode", () => {
        const config = parseConfig({
            ...serializeConfig(sample()),
            vm_mode: "incus-vm",
        });
        expect(config.vm_mode).toBe("incus-vm");
        expect(serializeConfig(config).vm_mode).toBe("incus-vm");
    });

    test("falls back to the default on an unknown vm mode", () => {
        expect(parseConfig({ vm_mode: "qemu" }).vm_mode).toBe("incus");
    });

    test("drops the disk limit when no VM is managed", () => {
        const config = { ...sample(), vm_mode: "none" as const };
        expect(serializeConfig(config).max_disk_size).toBeNull();
    });

    test("generates a nop team first", () => {
        const teams = generateTeams(3, true);
        expect(teams).toHaveLength(4);
        expect(teams[0].nop).toBe(true);
        expect(teams.filter((team) => team.nop)).toHaveLength(1);
        expect(new Set(teams.map((team) => team.token)).size).toBe(4);
    });
});

describe("topology", () => {
    test("a config without nodes is one all-in-one machine", () => {
        const nodes = effectiveNodes(sample());
        expect(nodes).toHaveLength(1);
        expect(nodes[0].roles).toEqual(["control", "vpn", "vm", "checker"]);
        expect(validateTopology(sample())).toEqual([]);
    });

    test("spreads the teams by weight", () => {
        const config: Config = {
            ...sample(),
            nodes: [
                { ...defaultNode(0), name: "a", weight: 2, address: "10.0.0.1" },
                { ...defaultNode(1), name: "b", weight: 1, address: "10.0.0.2" },
            ],
        };
        const vpn = assignTeams(config, "vpn");
        expect(vpn.a).toEqual([0, 1, 3, 4, 6]);
        expect(vpn.b).toEqual([2, 5]);
    });

    test("vulnboxes and tunnels are distributed independently", () => {
        const config: Config = {
            ...sample(),
            nodes: [
                {
                    ...defaultNode(0),
                    name: "front",
                    roles: ["control", "vpn", "checker"],
                    address: "10.0.0.1",
                    public_address: "ctf.example.com",
                },
                {
                    ...defaultNode(1),
                    name: "vms-1",
                    roles: ["vm"],
                    address: "10.0.0.2",
                    ssh: "root@10.0.0.2",
                    weight: 2,
                },
                {
                    ...defaultNode(2),
                    name: "vms-2",
                    roles: ["vm"],
                    address: "10.0.0.3",
                    ssh: "root@10.0.0.3",
                },
            ],
        };
        expect(assignTeams(config, "vpn")).toEqual({
            front: [0, 1, 2, 3, 4, 5, 6],
        });
        const vm = assignTeams(config, "vm");
        expect(vm["vms-1"]).toEqual([0, 1, 3, 4, 6]);
        expect(vm["vms-2"]).toEqual([2, 5]);
        // A VM node without a router of its own is a supported layout.
        expect(validateTopology(config)).toEqual([]);
    });

    test("vm_teams overrides the pinning for the vulnboxes only", () => {
        const config: Config = {
            ...sample(),
            nodes: [
                {
                    ...defaultNode(0),
                    name: "ctrl",
                    roles: ["control", "vpn", "vm"],
                    address: "10.0.0.1",
                    teams: [0, 1, 2, 3, 4, 5, 6],
                    vm_teams: [0, 1],
                },
                {
                    ...defaultNode(1),
                    name: "vm-a",
                    roles: ["vm"],
                    address: "10.0.0.2",
                    vm_teams: [2, 3, 4, 5, 6],
                },
            ],
        };
        expect(assignTeams(config, "vpn").ctrl).toEqual([0, 1, 2, 3, 4, 5, 6]);
        expect(assignTeams(config, "vm")).toEqual({
            ctrl: [0, 1],
            "vm-a": [2, 3, 4, 5, 6],
        });
    });

    test("reports the mistakes that actually break a deployment", () => {
        const config: Config = {
            ...sample(),
            nodes: [
                { ...defaultNode(0), name: "a", roles: ["control", "vpn"], address: "" },
                { ...defaultNode(1), name: "a", roles: ["control", "vm"], address: "10.0.0.2" },
                { ...defaultNode(2), name: "c", roles: ["checker", "storage"], address: "10.0.0.3" },
            ],
        };
        const warnings = validateTopology(config).join("\n");
        expect(warnings).toContain("declare the 'control' role");
        expect(warnings).toContain("Duplicated node name 'a'");
        expect(warnings).toContain("has no public_address");
        expect(warnings).toContain("Unknown roles");
        expect(warnings).toContain("has no ssh target");
    });

    test("a VM node with no VPN node anywhere is flagged", () => {
        const config: Config = {
            ...sample(),
            nodes: [
                { ...defaultNode(0), name: "a", roles: ["control", "vm"], address: "10.0.0.1" },
            ],
        };
        expect(validateTopology(config).join("\n")).toContain(
            "no node has the 'vpn' role",
        );
    });
});

describe("the control node", () => {
    test("is the first one, whatever the config says", () => {
        const config = parseConfig({
            nodes: [
                { name: "front", roles: ["vpn", "vm"] },
                { name: "edge", roles: ["control", "vpn"] },
            ],
        });
        expect(config.nodes[0].roles).toContain("control");
        expect(config.nodes[1].roles).not.toContain("control");
    });

    test("keeps the control role even when a config drops it", () => {
        const config = parseConfig({
            nodes: [{ name: "front", roles: ["vm"] }],
        });
        expect(config.nodes[0].roles).toEqual(["control", "vm"]);
    });

    test("does not gain the role twice", () => {
        const config = parseConfig({
            nodes: [{ name: "front", roles: ["control", "vpn"] }],
        });
        expect(
            config.nodes[0].roles.filter((role) => role === "control"),
        ).toHaveLength(1);
    });
});

describe("fields that stop applying", () => {
    test("a node losing the vpn role loses its public address", () => {
        const node = { ...defaultNode(1), public_address: "node2.example.com" };
        expect(rolesPatch(node, ["vm"])).toEqual({
            roles: ["vm"],
            public_address: "",
        });
    });

    test("keeping the vpn role keeps it", () => {
        const node = { ...defaultNode(1), public_address: "node2.example.com" };
        expect(rolesPatch(node, ["vpn", "vm"])).toEqual({ roles: ["vpn", "vm"] });
    });

    test("the router role counts as terminating tunnels", () => {
        const node = { ...defaultNode(1), public_address: "node2.example.com" };
        expect(rolesPatch(node, ["router"])).toEqual({ roles: ["router"] });
    });

    test("a node losing the checker role loses its concurrency", () => {
        const node = { ...defaultNode(1), checker_concurrency: 8 };
        expect(rolesPatch(node, ["vpn"])).toEqual({
            roles: ["vpn"],
            checker_concurrency: 0,
        });
    });

    test("a hidden public address never reaches the exported config", () => {
        const config = {
            ...sample(),
            nodes: [
                { ...defaultNode(0) },
                {
                    ...defaultNode(1),
                    roles: ["vm"],
                    address: "10.0.0.2",
                    public_address: "",
                },
            ],
        };
        const written = JSON.parse(configToJson(config));
        expect(written.nodes[1].public_address).toBeUndefined();
    });
});
