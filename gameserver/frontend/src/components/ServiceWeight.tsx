import { Badge, Tooltip } from "@mantine/core";

/** Every service is worth the same by default. When the organizers gave one a
 *  different multiplier the scoreboard has to say so, otherwise the totals do
 *  not add up from what is on screen. */
export const ServiceWeight = ({ weight }: { weight?: number }) => {
    if (weight == null || weight === 1) return null;
    return (
        <Tooltip
            label={`This service counts ×${weight} towards the score`}
            position="top"
            withArrow
        >
            <Badge
                ml="xs"
                size="sm"
                variant="light"
                color={weight > 1 ? "yellow" : "gray"}
            >
                ×{weight}
            </Badge>
        </Tooltip>
    );
};
