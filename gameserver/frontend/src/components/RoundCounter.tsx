import { Badge, Box, Chip, Progress, Text } from "@mantine/core"
import { useStatusQuery } from "../scripts/query"
import { useInterval } from "@mantine/hooks"
import { useEffect, useState } from "react"
import { getDateFormatted, secondDurationToString } from "../scripts/time"


export const RoundCounter = () => {
    const config = useStatusQuery()
    
    const [roundInfo, setRoundInfo] = useState({
        startTime: new Date(0),
        roundLen: 0,
        currentRound: -1,
        currentRoundPercent: 0,
        hasStarted: false,
        timeForNextRound: 0,
        hasEnded: false,
        endTime: null as Date | null
    })

    const updateRoundInfo = () => {
        if (config.data == null || config.isFetching) return
        const startGame = new Date(config.data.start)
        const endGame = config.data.end != null ? new Date(config.data.end) : null
        const now = new Date()
        const roundLen = config.data.roundTime * 1000
        const nextRoundAt = new Date(startGame.getTime() + (config.data.current_round+2)*roundLen)
        const timeForNextRound = nextRoundAt.getTime() - now.getTime()
        const nextRoundPercent = Math.min(100, 100 - ((timeForNextRound / roundLen) * 100))
        setRoundInfo({
            startTime: new Date(config.data.start),
            roundLen: config.data.roundTime,
            currentRound: config.data.current_round,
            currentRoundPercent: nextRoundPercent,
            hasStarted: startGame < now,
            timeForNextRound: (timeForNextRound <1000?0:timeForNextRound)/1000,
            hasEnded: endGame != null && endGame < now,
            endTime: config.data.end?new Date(config.data.end??0):null
        })
    }

    const timerScheduler = useInterval(updateRoundInfo, 1000, { autoInvoke: true })
    
    useEffect(() => {
        timerScheduler.start()
        return () => timerScheduler.stop()
    },[timerScheduler])


    useEffect(updateRoundInfo, [config.isFetching])

    const lastsTimeString = secondDurationToString(roundInfo.timeForNextRound)

    return config.isSuccess?<Box>
        <Text size="md">{ !roundInfo.hasStarted ? "Game has not started yet" :roundInfo.hasEnded ? "Game has ended!" : roundInfo.currentRound==-1 ? "Game has started!" : `Round: ${config.data.current_round} - next round ${lastsTimeString?'in '+lastsTimeString:'soon...'}` }</Text>
        <Progress size="lg" value={roundInfo.hasEnded ? 100 : config.data.current_round >= 0?roundInfo.currentRoundPercent:0} color="red" animated />
        <Box className="center-flex" mt="sm">
            <Text size="md"><Badge size="md" radius="md" color="teal" >Starts - {getDateFormatted(roundInfo.startTime.toISOString())}</Badge> </Text>
            <Box style={{flex:1}}/>
            <Text size="md"><Badge size="md" radius="md" color="teal" >Ends - {roundInfo.endTime?getDateFormatted(roundInfo.endTime?.toISOString()??""):"Will never End"}</Badge> </Text>
        </Box>
    </Box>:<Progress size="lg" color="red" value={0}/>
}