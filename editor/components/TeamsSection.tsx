"use client";

import {
    ActionIcon,
    Badge,
    Button,
    Group,
    NumberInput,
    ScrollArea,
    Switch,
    Table,
    Text,
    TextInput,
    Tooltip,
} from "@mantine/core";
import { NumberField } from "./NumberField";
import { useState } from "react";
import { MdAdd, MdDelete, MdRefresh } from "react-icons/md";
import { MdGroups } from "react-icons/md";
import { Config, Team, generateTeams, randomToken } from "@/lib/config";
import { SectionCard } from "./SectionCard";

export const TeamsSection = ({
    config,
    update,
}: {
    config: Config;
    update: (patch: Partial<Config>) => void;
}) => {
    const [count, setCount] = useState<number | string>(
        Math.max(config.teams.filter((team) => !team.nop).length, 4),
    );
    const [withNop, setWithNop] = useState(
        config.teams.some((team) => team.nop) || config.teams.length === 0,
    );

    const setTeam = (index: number, patch: Partial<Team>) => {
        const teams = config.teams.map((team, i) =>
            i === index ? { ...team, ...patch } : team,
        );
        update({ teams });
    };

    const removeTeam = (index: number) =>
        update({ teams: config.teams.filter((_, i) => i !== index) });

    const addTeam = () => {
        const nextId = config.teams.reduce(
            (max, team) => Math.max(max, team.id + 1),
            0,
        );
        update({
            teams: [
                ...config.teams,
                {
                    id: nextId,
                    name: `Team ${nextId}`,
                    token: randomToken(),
                    nop: false,
                    image: "",
                },
            ],
        });
    };

    return (
        <SectionCard
            title="Teams"
            icon={<MdGroups size={20} />}
            description="Each team gets a vulnbox at 10.60.<id>.1 and a submission token. The NOP team is the organizers' reference machine: it is checked but neither scores nor loses points."
            actions={
                <Badge variant="light" size="lg">
                    {config.teams.filter((team) => !team.nop).length} playing
                </Badge>
            }
        >
            <Group align="end" mb="md" wrap="wrap">
                <NumberInput
                    label="Number of teams"
                    min={0}
                    max={249}
                    w={180}
                    value={count}
                    onChange={setCount}
                />
                <Switch
                    label="Include a NOP team"
                    mb={8}
                    checked={withNop}
                    onChange={(event) => setWithNop(event.currentTarget.checked)}
                />
                <Button
                    onClick={() =>
                        update({
                            teams: generateTeams(Number(count) || 0, withNop),
                        })
                    }
                >
                    Generate teams
                </Button>
                <Button
                    variant="light"
                    leftSection={<MdAdd />}
                    onClick={addTeam}
                >
                    Add one
                </Button>
            </Group>

            {config.teams.length === 0 ? (
                <Text c="dimmed">
                    No team yet: generate them, or import an existing
                    configuration.
                </Text>
            ) : (
                <ScrollArea.Autosize mah={460}>
                    <Table striped highlightOnHover verticalSpacing="xs">
                        <Table.Thead>
                            <Table.Tr>
                                <Table.Th w={70}>ID</Table.Th>
                                <Table.Th>Name</Table.Th>
                                <Table.Th>Logo</Table.Th>
                                <Table.Th>Token</Table.Th>
                                <Table.Th w={80}>NOP</Table.Th>
                                <Table.Th w={50} />
                            </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                            {config.teams.map((team, index) => (
                                <Table.Tr key={index}>
                                    <Table.Td>
                                        <NumberField
                                            size="xs"
                                            min={0}
                                            max={249}
                                            value={team.id}
                                            fallback={0}
                                            onValueChange={(value) =>
                                                setTeam(index, { id: value })
                                            }
                                        />
                                    </Table.Td>
                                    <Table.Td>
                                        <TextInput
                                            size="xs"
                                            value={team.name}
                                            onChange={(event) =>
                                                setTeam(index, {
                                                    name: event.currentTarget
                                                        .value,
                                                })
                                            }
                                        />
                                    </Table.Td>
                                    <Table.Td>
                                        <TextInput
                                            size="xs"
                                            placeholder="logo.png or https://..."
                                            value={team.image}
                                            onChange={(event) =>
                                                setTeam(index, {
                                                    image: event.currentTarget
                                                        .value,
                                                })
                                            }
                                        />
                                    </Table.Td>
                                    <Table.Td>
                                        <TextInput
                                            size="xs"
                                            classNames={{ input: "mono" }}
                                            value={team.token}
                                            onChange={(event) =>
                                                setTeam(index, {
                                                    token: event.currentTarget
                                                        .value,
                                                })
                                            }
                                            rightSection={
                                                <Tooltip label="New token">
                                                    <ActionIcon
                                                        size="sm"
                                                        variant="subtle"
                                                        onClick={() =>
                                                            setTeam(index, {
                                                                token: randomToken(),
                                                            })
                                                        }
                                                    >
                                                        <MdRefresh />
                                                    </ActionIcon>
                                                </Tooltip>
                                            }
                                        />
                                    </Table.Td>
                                    <Table.Td>
                                        <Switch
                                            checked={team.nop}
                                            onChange={(event) =>
                                                setTeam(index, {
                                                    nop: event.currentTarget
                                                        .checked,
                                                })
                                            }
                                        />
                                    </Table.Td>
                                    <Table.Td>
                                        <ActionIcon
                                            color="red"
                                            variant="subtle"
                                            onClick={() => removeTeam(index)}
                                            aria-label="Remove team"
                                        >
                                            <MdDelete />
                                        </ActionIcon>
                                    </Table.Td>
                                </Table.Tr>
                            ))}
                        </Table.Tbody>
                    </Table>
                </ScrollArea.Autosize>
            )}
        </SectionCard>
    );
};
