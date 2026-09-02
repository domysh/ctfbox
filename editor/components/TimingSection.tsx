"use client";

import { Alert, SimpleGrid, Text, TextInput } from "@mantine/core";
import { NumberField } from "./NumberField";
import { MdAcUnit, MdSchedule } from "react-icons/md";
import { Config } from "@/lib/config";
import { fromLocalInput, humanDuration, toLocalInput } from "@/lib/time";
import { SectionCard } from "./SectionCard";

export const TimingSection = ({
    config,
    update,
}: {
    config: Config;
    update: (patch: Partial<Config>) => void;
}) => (
    <SectionCard
        title="Schedule"
        icon={<MdSchedule size={18} />}
        description="When the game runs, how long a round lasts, and when the ranking stops being public."
    >
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            <TextInput
                type="datetime-local"
                label="Start time"
                description="Empty means now + grace time, decided on the first boot"
                value={toLocalInput(config.start_time)}
                onChange={(event) =>
                    update({ start_time: fromLocalInput(event.currentTarget.value) })
                }
            />
            <TextInput
                type="datetime-local"
                label="End time"
                description="Empty means the game never ends on its own"
                value={toLocalInput(config.end_time)}
                onChange={(event) =>
                    update({ end_time: fromLocalInput(event.currentTarget.value) })
                }
            />
            <NumberField
                label="Grace time (seconds)"
                description={`Network locked before the start: ${humanDuration(config.grace_time)}`}
                min={0}
                value={config.grace_time}
                fallback={0}
                onValueChange={(value) => update({ grace_time: value })}
            />
            <NumberField
                label="Tick time (seconds)"
                description={`One round lasts ${humanDuration(config.tick_time)}`}
                min={5}
                value={config.tick_time}
                fallback={120}
                onValueChange={(value) => update({ tick_time: value })}
            />
        </SimpleGrid>

        <Alert
            mt="lg"
            color="blue"
            icon={<MdAcUnit size={18} />}
            title="Scoreboard freeze"
        >
            <Text size="sm" mb="sm">
                From this moment the ranking stops moving: points, stolen and
                lost flags stay at the freeze round, while SLA and service
                status keep updating live. Leave it empty to never freeze, or to
                decide during the game from the admin panel.
            </Text>
            <TextInput
                type="datetime-local"
                w={280}
                value={toLocalInput(config.scoreboard_freeze_time)}
                onChange={(event) =>
                    update({
                        scoreboard_freeze_time: fromLocalInput(
                            event.currentTarget.value,
                        ),
                    })
                }
            />
        </Alert>
    </SectionCard>
);
