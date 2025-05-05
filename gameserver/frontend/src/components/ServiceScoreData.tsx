import { Box, Code, Divider, Space, Tooltip, Text } from "@mantine/core";
import { TeamServiceScore } from "../scripts/query";
import { ImTarget } from "react-icons/im";
import { FaCircle, FaGlobe, FaPlug, FaPlus, FaWrench } from "react-icons/fa6";
import { FaSearch, FaShieldAlt } from "react-icons/fa";
import { IoSpeedometer } from "react-icons/io5";
import { modals } from "@mantine/modals";
import { FaStar } from "react-icons/fa";
import { DiffArrow } from "./DiffArrow";


export const ServiceScoreData = ({ score }: { score?: TeamServiceScore }) => {

    if (!score) return <></>

    const slaOk = score.sla_check == 101 && score.get_flag == 101 && score.put_flag == 101
    const slaUnknown = score.sla_check == 0 && score.get_flag == 0 && score.put_flag == 0

    const showDetailModal = (title:string, msg:string) => {
        modals.open({
            title: title,
            children: (<Code block>{msg}</Code>),
            size: "lg",
            centered: true
        });
    }

    return <>
        <Box display="flex" style={{ alignItems: "center", justifyContent: "space-between", width: "100%" }}>
            <Box display="flex" style={{ alignItems: "center", textWrap: "nowrap" }} pr="xl">
                <FaGlobe size={16} /><Space w="xs" /><Text>{score.final_score.toFixed(2)}</Text>
            </Box>
            <DiffArrow diff={score.diff_final_score} />
        </Box>
        <Divider my={6} />
        <Box display="flex" style={{ alignItems: "center", justifyContent: "space-between", width: "100%" }}>
            <Box display="flex" style={{ alignItems: "center", textWrap: "nowrap" }} pr="xl">
                <FaStar size={16} /><Space w="xs" /><Text>{score.score.toFixed(2)}</Text>
            </Box>
            <DiffArrow diff={score.diff_score} />
        </Box>
        <Box display="flex" style={{ alignItems: "center", justifyContent: "space-between", width: "100%" }}>
            <Box display="flex" style={{ alignItems: "center", textWrap: "nowrap" }} pr="xl">
                <ImTarget size={16} /><Space w="xs" /> <Text>{score.offensive_points==0?"":"+"}{score.offensive_points.toFixed(2)} ({score.stolen_flags==0?"":"+"}{score.stolen_flags})</Text>
            </Box>
            <DiffArrow diff={score.diff_offensive_points} text={`${score.diff_offensive_points==0?"":"+"}${score.diff_offensive_points.toFixed(2)} (${score.diff_stolen_flags==0?"":"+"}${score.diff_stolen_flags})`} />
        </Box>
        <Box display="flex" style={{ alignItems: "center", justifyContent: "space-between", width: "100%" }}>
            <Box display="flex" style={{ alignItems: "center", textWrap: "nowrap" }} pr="xl">
                <FaShieldAlt size={16} /><Space w="xs" /> <Text>{score.defensive_points.toFixed(2)} ({score.lost_flags==0?"":"-"}{score.lost_flags})</Text>
            </Box>
            <DiffArrow diff={score.diff_defensive_points} text={`${score.diff_defensive_points.toFixed(2)} (${score.diff_lost_flags==0?"":"-"}${score.diff_lost_flags})`} />
        </Box>
        <Box display="flex" style={{ alignItems: "center", justifyContent: "space-between", width: "100%" }}>
            <Box display="flex" style={{ alignItems: "center", textWrap: "nowrap" }} pr="xl">
                <IoSpeedometer size={16} /><Space w="xs" /><Text>{(score.sla*100).toFixed(2)}%</Text><Space w="xs" />
                <Tooltip label={`Rounds up ${score.ticks_up}/${score.ticks_down+score.ticks_up}`} position="top" withArrow>
                    <Box>
                        <FaCircle size={16} style={{ color: slaOk ? "green" : slaUnknown ? "gray" : "red" }} />
                    </Box>
                </Tooltip>
            </Box>
            <DiffArrow diff={Math.round(score.diff_sla*10000)/100} />
        </Box>
        <Box display="flex" style={{ alignItems: "center", justifyContent: "space-between", width: "100%" }}>
            <Box display="flex" style={{ alignItems: "center", textWrap: "nowrap" }}>
                <FaWrench size={16} /><Space w="xs" />
                <Box p={3} className="center-flex" style={{ borderRadius: "100px" }}>
                    <Tooltip label={slaUnknown?"SLA CHECK":"SLA CHECK: "+score.sla_check_msg.substring(0,150)} position="top" withArrow color={slaUnknown?"gray":score.sla_check == 101 ? "green": "red"}>
                        <Box
                            py={4} px={10}
                            style={{ backgroundColor: slaUnknown?"gray":score.sla_check == 101 ? "green": "red", borderTopLeftRadius: 6, borderBottomLeftRadius: 6 }}
                            className="center-flex"
                            onClick={slaUnknown ? ()=>{}:()=>showDetailModal(`SLA CHECK on ${score.service}`, score.sla_check_msg)}
                        >
                            <FaPlug size={14}/>
                        </Box>
                    </Tooltip>
                    <Tooltip label={slaUnknown?"PUT FLAG":"PUT FLAG: "+score.put_flag_msg.substring(0,150)} position="top" withArrow color={slaUnknown?"gray":score.put_flag == 101 ? "green": "red"}>
                        <Box
                            py={4} px={10}
                            style={{ backgroundColor: slaUnknown?"gray":score.put_flag == 101 ? "green": "red"}}
                            className="center-flex"
                            onClick={slaUnknown ? ()=>{}:()=>showDetailModal(`PUT FLAG on ${score.service}`, score.put_flag_msg)}
                        >
                            <FaPlus size={14} />
                        </Box> 
                    </Tooltip>
                    <Tooltip label={slaUnknown?"GET FLAG":"GET FLAG: "+score.get_flag_msg.substring(0,150)} position="top" withArrow color={slaUnknown?"gray":score.get_flag == 101 ? "green": "red"}>
                        <Box
                            py={4} px={12}
                            style={{ backgroundColor: slaUnknown?"gray":score.get_flag == 101 ? "green": "red", borderTopRightRadius: 6, borderBottomRightRadius: 6 }}
                            className="center-flex"
                            onClick={slaUnknown ? ()=>{}:()=>showDetailModal(`GET FLAG on ${score.service}`, score.get_flag_msg)}
                        >
                            <FaSearch size={14} />
                        </Box>
                    </Tooltip>
                </Box>
            </Box>
        </Box>
    </>
}