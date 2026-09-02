import { ALL_ROLES, Config, Node } from "./config";

/**
 * The topology helpers below mirror `effective_nodes`, `assign_teams` and
 * `validate_topology` in run.py, so that what the editor previews is exactly
 * what the deployment will do.
 */

export const effectiveNodes = (config: Config): Node[] => {
    if (config.nodes.length === 0) {
        return [
            {
                name: "main",
                roles: [...ALL_ROLES],
                address: config.server_addr,
                public_address: config.server_addr,
                ssh: "",
                path: "~/ctfbox",
                weight: 1,
                checker_concurrency: 0,
                teams: [],
                vm_teams: [],
            },
        ];
    }
    const nodes = config.nodes.map((node) => ({
        ...node,
        roles: node.roles.length > 0 ? node.roles : [...ALL_ROLES],
        public_address: node.public_address || node.address,
    }));
    if (!nodes.some((node) => node.roles.includes("control"))) {
        nodes[0] = { ...nodes[0], roles: [...nodes[0].roles, "control"] };
    }
    return nodes;
};

const hasRole = (node: Node, role: string) =>
    node.roles.includes(role) || (role === "vpn" && node.roles.includes("router"));

const pinnedTeams = (node: Node, role: string): number[] =>
    role === "vm" && node.vm_teams.length > 0 ? [...node.vm_teams] : [...node.teams];

/** Weighted round robin, identical to the one in run.py and confgen.py. */
export const assignTeams = (
    config: Config,
    role: "vpn" | "vm" | "checker" | "control",
): Record<string, number[]> => {
    const nodes = effectiveNodes(config).filter((node) => hasRole(node, role));
    if (nodes.length === 0) return {};

    const assignment: Record<string, number[]> = {};
    for (const node of nodes) assignment[node.name] = pinnedTeams(node, role);

    const already = new Set(Object.values(assignment).flat());
    const slots: string[] = [];
    for (const node of nodes)
        for (let i = 0; i < Math.max(node.weight, 1); i++) slots.push(node.name);

    let index = 0;
    for (const team of config.teams) {
        if (already.has(team.id)) continue;
        assignment[slots[index % slots.length]].push(team.id);
        index++;
    }
    return assignment;
};

export const validateTopology = (config: Config): string[] => {
    const nodes = effectiveNodes(config);
    const warnings: string[] = [];

    const controls = nodes
        .filter((node) => node.roles.includes("control"))
        .map((node) => node.name);
    if (controls.length > 1) {
        warnings.push(
            `${controls.length} nodes declare the 'control' role (${controls.join(", ")}): exactly one node owns the database and the game server.`,
        );
    }

    const seen = new Set<string>();
    for (const node of nodes) {
        if (seen.has(node.name))
            warnings.push(`Duplicated node name '${node.name}'.`);
        seen.add(node.name);
        if (!node.name.trim()) warnings.push("A node has an empty name.");
        if (
            node.roles.includes("checker") &&
            !node.roles.includes("control") &&
            !node.ssh
        ) {
            warnings.push(
                `Checker node '${node.name}' has no ssh target: deploy it by hand with './run.py node up ${node.name}' on that machine.`,
            );
        }
        if (!node.address && !node.public_address)
            warnings.push(`Node '${node.name}' has no address.`);
        if (hasRole(node, "vpn") && !(node.public_address || node.address)) {
            warnings.push(
                `VPN node '${node.name}' has no public_address: the players and the vulnboxes assigned to it would not know where to connect.`,
            );
        }
    }

    const hasVm = nodes.some((node) => node.roles.includes("vm"));
    const hasVpn = nodes.some((node) => hasRole(node, "vpn"));
    if (hasVm && !hasVpn) {
        warnings.push(
            "Some nodes host VMs but no node has the 'vpn' role: the vulnboxes would have no endpoint to dial into.",
        );
    }

    const unknown = new Set<string>();
    for (const node of nodes)
        for (const role of node.roles)
            if (!ALL_ROLES.includes(role as never) && role !== "router")
                unknown.add(role);
    if (unknown.size > 0) {
        warnings.push(
            `Unknown roles ${JSON.stringify([...unknown].sort())}: valid roles are ${JSON.stringify(ALL_ROLES)}.`,
        );
    }

    if (config.nodes.length > 0 && config.teams.length > 0) {
        const vmAssigned = new Set(Object.values(assignTeams(config, "vm")).flat());
        if (config.vm_mode !== "none" && vmAssigned.size === 0) {
            warnings.push(
                "No node has the 'vm' role: nothing would host the vulnboxes.",
            );
        }
    }
    return warnings;
};

export type NodeSummary = {
    node: Node;
    vpnTeams: number[];
    vmTeams: number[];
};

export const topologySummary = (config: Config): NodeSummary[] => {
    const vpn = assignTeams(config, "vpn");
    const vm = assignTeams(config, "vm");
    return effectiveNodes(config).map((node) => ({
        node,
        vpnTeams: (vpn[node.name] ?? []).slice().sort((a, b) => a - b),
        vmTeams: (vm[node.name] ?? []).slice().sort((a, b) => a - b),
    }));
};
