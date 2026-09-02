"use client";

import {
    SimpleGrid,
    Switch,
    Text,
    TextInput,
} from "@mantine/core";
import { NumberField } from "./NumberField";
import { GiCrosshair } from "react-icons/gi";
import { RiRadarLine } from "react-icons/ri";
import { FaNetworkWired } from "react-icons/fa6";
import { Config } from "@/lib/config";
import { SectionCard } from "./SectionCard";

type Props = {
    config: Config;
    update: (patch: Partial<Config>) => void;
};

export const GameplaySection = ({ config, update }: Props) => (
    <SectionCard
        title="Scoring"
        icon={<GiCrosshair size={18} />}
        description="Flag lifetime, service points and the limits applied to the submission endpoint."
    >
        <SimpleGrid cols={{ base: 1, md: 2, lg: 4 }} spacing="md">
            <NumberField
                label="Flag expiration (ticks)"
                description="How many rounds a flag stays worth points"
                min={1}
                value={config.flag_expire_ticks}
                fallback={5}
                onValueChange={(value) => update({ flag_expire_ticks: value })}
            />
            <NumberField
                label="Initial service score"
                description="Points every service starts the game with"
                min={1}
                value={config.initial_service_score}
                fallback={5000}
                onValueChange={(value) =>
                    update({ initial_service_score: value })
                }
            />
            <NumberField
                label="Max flags per request"
                description="Extra flags in a submission are ignored"
                min={1}
                value={config.max_flags_per_request}
                fallback={1}
                onValueChange={(value) =>
                    update({ max_flags_per_request: value })
                }
            />
            <NumberField
                label="Submission rate limit (s)"
                description="0 disables the limit"
                min={0}
                step={0.01}
                decimalScale={3}
                value={config.submission_timeout ?? 0}
                fallback={0}
                onValueChange={(value) =>
                    update({ submission_timeout: value > 0 ? value : null })
                }
            />
        </SimpleGrid>
    </SectionCard>
);

export const CheckerSection = ({ config, update }: Props) => (
    <SectionCard
        title="Checkers and monitoring"
        icon={<RiRadarLine size={18} />}
        description="Checker jobs are pulled by the workers, so these are per worker limits: the control node always runs one, and every extra checker node adds its own slots."
    >
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            <NumberField
                label="Checker timeout (seconds)"
                description="How long a single check may take"
                min={5}
                value={config.checker_timeout}
                fallback={30}
                onValueChange={(value) => update({ checker_timeout: value })}
            />
            <NumberField
                label="Checker concurrency"
                description="Parallel checks per worker, 0 picks it from the CPUs"
                min={0}
                value={config.checker_concurrency}
                fallback={0}
                onValueChange={(value) =>
                    update({ checker_concurrency: value })
                }
            />
        </SimpleGrid>
        <Switch
            mt="lg"
            label="Per team traffic monitoring"
            description="The routers account the traffic of every team pair and push it to the admin panel"
            checked={config.traffic_monitor}
            onChange={(event) =>
                update({ traffic_monitor: event.currentTarget.checked })
            }
            thumbIcon={<FaNetworkWired size={9} />}
        />
        {!config.traffic_monitor && (
            <Text size="xs" c="dimmed" mt="xs">
                The attack graph built from the submitted flags stays available
                either way.
            </Text>
        )}
        <Switch
            mt="lg"
            label="Full packet capture"
            description="Every router keeps a rotating capture of the game interface, downloadable from the admin panel filtered by team, round or interval"
            checked={config.pcap}
            onChange={(event) => update({ pcap: event.currentTarget.checked })}
            thumbIcon={<FaNetworkWired size={9} />}
        />
        {config.pcap && (
            <NumberField
                mt="sm"
                maw={280}
                label="Capture ring size (MB per router)"
                description="The oldest files are dropped once this is reached, so the disk usage is bounded"
                min={16}
                step={64}
                value={config.pcap_max_size}
                fallback={512}
                onValueChange={(value) => update({ pcap_max_size: value })}
            />
        )}
    </SectionCard>
);
