"use client";

import {
    ActionIcon,
    Group,
    SimpleGrid,
    Switch,
    TextInput,
    Tooltip,
} from "@mantine/core";
import { NumberField } from "./NumberField";
import { MdRefresh } from "react-icons/md";
import { FaServer, FaShieldHalved } from "react-icons/fa6";
import { Config, randomToken } from "@/lib/config";
import { SectionCard } from "./SectionCard";

type Props = {
    config: Config;
    update: (patch: Partial<Config>) => void;
};

const TokenInput = ({
    label,
    description,
    value,
    onChange,
}: {
    label: string;
    description: string;
    value: string;
    onChange: (value: string) => void;
}) => (
    <TextInput
        label={label}
        description={description}
        classNames={{ input: "mono" }}
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
        rightSection={
            <Tooltip label="Generate a new random token">
                <ActionIcon
                    variant="subtle"
                    onClick={() => onChange(randomToken())}
                    aria-label="Regenerate token"
                >
                    <MdRefresh />
                </ActionIcon>
            </Tooltip>
        }
    />
);

export const GeneralSection = ({ config, update }: Props) => (
    <SectionCard
        title="Server"
        icon={<FaServer />}
        description="How the players reach the infrastructure. The control room at /admin has no password and no setting: it answers only to the admin WireGuard profiles."
    >
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            <TextInput
                label="Server address"
                description="Public hostname or IP the players connect to"
                placeholder="ctf.example.com"
                required
                value={config.server_addr}
                onChange={(event) =>
                    update({ server_addr: event.currentTarget.value })
                }
            />
            <TextInput
                label="DNS"
                description="Resolver used inside the game network"
                value={config.dns}
                onChange={(event) => update({ dns: event.currentTarget.value })}
            />
            <NumberField
                label="WireGuard port"
                description="UDP port of the player tunnels"
                min={1}
                max={65535}
                value={config.wireguard_port}
                fallback={51000}
                onValueChange={(value) => update({ wireguard_port: value })}
            />
            <NumberField
                label="WireGuard profiles per team"
                description="How many people of a team can connect at once"
                min={1}
                value={config.wireguard_profiles}
                fallback={1}
                onValueChange={(value) => update({ wireguard_profiles: value })}
            />
            <TokenInput
                label="Gameserver token"
                description="Shared by the checkers, the workers and the router agents"
                value={config.gameserver_token}
                onChange={(gameserver_token) => update({ gameserver_token })}
            />

        </SimpleGrid>

        <Group mt="lg" align="start" gap="xl" wrap="wrap">
            <div>
                <Switch
                    label="Expose the scoreboard outside the game network"
                    checked={config.gameserver_exposed_port !== null}
                    onChange={(event) =>
                        update({
                            gameserver_exposed_port: event.currentTarget.checked
                                ? "127.0.0.1:8888"
                                : null,
                        })
                    }
                />
                {config.gameserver_exposed_port !== null && (
                    <TextInput
                        mt="xs"
                        w={240}
                        placeholder="127.0.0.1:8888"
                        value={config.gameserver_exposed_port}
                        onChange={(event) =>
                            update({
                                gameserver_exposed_port:
                                    event.currentTarget.value,
                            })
                        }
                    />
                )}
            </div>
            <div>
                <Switch
                    label="Enable the credentials service"
                    checked={config.credential_server !== null}
                    onChange={(event) =>
                        update({
                            credential_server: event.currentTarget.checked
                                ? "127.0.0.1:4040"
                                : null,
                        })
                    }
                />
                {config.credential_server !== null && (
                    <TextInput
                        mt="xs"
                        w={240}
                        placeholder="127.0.0.1:4040"
                        value={config.credential_server}
                        onChange={(event) =>
                            update({
                                credential_server: event.currentTarget.value,
                            })
                        }
                    />
                )}
            </div>
            <Switch
                label="Debug mode"
                description="Verbose logs and permissive CORS"
                checked={config.debug}
                onChange={(event) =>
                    update({ debug: event.currentTarget.checked })
                }
                thumbIcon={<FaShieldHalved size={9} />}
            />
        </Group>
    </SectionCard>
);
