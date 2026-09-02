"use client";

import {
    Alert,
    SegmentedControl,
    SimpleGrid,
    Stack,
    Switch,
    Text,
    TextInput,
} from "@mantine/core";
import { FaMicrochip } from "react-icons/fa6";
import { Config, VmMode } from "@/lib/config";
import { SectionCard } from "./SectionCard";

const MODE_HELP: Record<VmMode, string> = {
    incus: "Each vulnbox is an Incus system container inside a dedicated sandbox: it shares the host kernel, boots in seconds and is cheap. The safe default.",
    "incus-vm":
        "Each vulnbox is a real Incus virtual machine with its own kernel. The strongest isolation between the teams and the host, but it needs KVM on every VM node and costs noticeably more RAM, disk and boot time.",
    privileged:
        "Each vulnbox is a privileged Docker container: faster, but a player who escapes it owns the host. Only for trusted players.",
    none: "CTFBox runs no vulnbox at all: you bring your own machines and connect them with the generated WireGuard profiles.",
};

export const ResourcesSection = ({
    config,
    update,
}: {
    config: Config;
    update: (patch: Partial<Config>) => void;
}) => (
    <SectionCard
        title="Vulnboxes"
        icon={<FaMicrochip size={16} />}
        description="How the team machines are created and how much they are allowed to use."
    >
        <Stack gap="md">
            <div>
                <Text size="sm" fw={500} mb={6}>
                    VM mode
                </Text>
                <SegmentedControl
                    data={[
                        { value: "incus", label: "Incus container" },
                        { value: "incus-vm", label: "Incus VM" },
                        { value: "privileged", label: "Privileged Docker" },
                        { value: "none", label: "None" },
                    ]}
                    value={config.vm_mode}
                    onChange={(value) => update({ vm_mode: value as VmMode })}
                />
                <Text size="xs" c="dimmed" mt={6}>
                    {MODE_HELP[config.vm_mode]}
                </Text>
            </div>

            {config.vm_mode !== "none" && (
                <>
                    <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
                        <TextInput
                            label="CPUs per VM"
                            description="Cores each team box may use"
                            value={config.max_vm_cpus}
                            onChange={(event) =>
                                update({ max_vm_cpus: event.currentTarget.value })
                            }
                        />
                        <TextInput
                            label="Memory per VM"
                            description="Docker style size, for example 2G"
                            placeholder="2G"
                            value={config.max_vm_mem}
                            onChange={(event) =>
                                update({ max_vm_mem: event.currentTarget.value })
                            }
                        />
                        <TextInput
                            label="Network bandwidth per team"
                            description="Rate limit applied on the router"
                            placeholder="50mbit"
                            value={config.network_limit_bandwidth}
                            onChange={(event) =>
                                update({
                                    network_limit_bandwidth:
                                        event.currentTarget.value,
                                })
                            }
                        />
                    </SimpleGrid>

                    <div>
                        <Switch
                            label="Limit the disk size of each VM"
                            checked={config.max_disk_size !== null}
                            onChange={(event) =>
                                update({
                                    max_disk_size: event.currentTarget.checked
                                        ? "30G"
                                        : null,
                                })
                            }
                        />
                        {config.max_disk_size !== null && (
                            <TextInput
                                mt="xs"
                                w={200}
                                placeholder="30G"
                                value={config.max_disk_size}
                                onChange={(event) =>
                                    update({
                                        max_disk_size: event.currentTarget.value,
                                    })
                                }
                            />
                        )}
                        {config.vm_mode === "privileged" &&
                            config.max_disk_size !== null && (
                                <Alert color="yellow" mt="sm">
                                    In privileged mode the disk limit needs the
                                    Docker storage driver to sit on an XFS
                                    filesystem with pquota enabled.
                                </Alert>
                            )}
                        {config.vm_mode === "incus-vm" && (
                            <Alert color="blue" mt="sm">
                                A virtual machine gets a real disk of this size,
                                so plan for it on every node hosting vulnboxes:
                                unlike a container, it is reserved up front.
                            </Alert>
                        )}
                    </div>
                </>
            )}
        </Stack>
    </SectionCard>
);
