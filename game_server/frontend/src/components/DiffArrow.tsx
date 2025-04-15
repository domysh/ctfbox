import { ActionIcon, Box, Text } from "@mantine/core"
import { FaArrowDown, FaArrowUp, FaMinus } from "react-icons/fa6"

export const DiffArrow = ({ diff, text }: { diff: number, text?:string }) => {
    const color = diff > 0 ? "green" : diff < 0 ? "red" : "grey"
    const icon = diff > 0 ? <FaArrowUp /> : diff < 0 ? <FaArrowDown /> : <FaMinus />
    return <Box className="center-flex">
        <Text c={color} style={{ textWrap: "nowrap" }} >
            {!text && diff > 0?"+":""}{text??diff.toFixed(2)}
        </Text>
        <ActionIcon variant="transparent" color={color} style={{ cursor: "default" }} onClick={(e) => e.stopPropagation()} >
            {icon}  
        </ActionIcon>
    </Box>

}