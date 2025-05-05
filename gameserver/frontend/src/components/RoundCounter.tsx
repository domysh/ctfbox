import { Badge, Box, Progress, Text } from "@mantine/core"
import { useStatusQuery } from "../scripts/query"
import { useInterval } from "@mantine/hooks"
import { useEffect, useState } from "react"
import { getDateFormatted, secondDurationToString } from "../scripts/time"


export const RoundCounter = () => {
    const config = useStatusQuery()
    
    const [roundInfo, setRoundInfo] = useState({
        startGraceTime: new Date(0),
        startTime: new Date(0),
        roundLen: 0,
        currentRound: -1,
        currentRoundPercent: 0,
        isGrace: false,
        hasStarted: false,
        timeForNextRound: 0,
        hasEnded: false,
        endTime: null as Date | null,
        hasInit: false,
    })

    const updateRoundInfo = () => {
        if (config.data == null || config.isFetching) return
        const startGrace = new Date(config.data.start_grace)
        const startGame = new Date(config.data.start)
        const endGame = config.data.end != null ? new Date(config.data.end) : null
        const now = new Date()
        const roundLen = config.data.roundTime * 1000
        const nextRoundAt = new Date(startGame.getTime() + (config.data.current_round+2)*roundLen)
        const timeForNextRound = nextRoundAt.getTime() - now.getTime()
        const nextRoundPercent = Math.min(100, 100 - ((timeForNextRound / roundLen) * 100))
        setRoundInfo({
            startGraceTime: startGrace,
            startTime: new Date(config.data.start),
            roundLen: config.data.roundTime,
            currentRound: config.data.current_round,
            currentRoundPercent: nextRoundPercent,
            hasStarted: startGame < now,
            timeForNextRound: (timeForNextRound <1000?0:timeForNextRound)/1000,
            hasEnded: endGame != null && endGame < now,
            endTime: config.data.end?new Date(config.data.end??0):null,
            isGrace: startGrace <= now && startGame > now,
            hasInit: now >= startGrace,
        })
    }

    const timerScheduler = useInterval(updateRoundInfo, 1000, { autoInvoke: true })
    
    useEffect(() => {
        timerScheduler.start()
        return () => timerScheduler.stop()
    },[timerScheduler])


    useEffect(updateRoundInfo, [config.isFetching])

    const lastsTimeString = secondDurationToString(roundInfo.timeForNextRound)

    const genInfoText = () => {
        if (!roundInfo.hasInit){
            if (roundInfo.startGraceTime.getTime() == roundInfo.startTime.getTime()){
                return <Box style={{display:"flex", flexDirection:"row", alignItems:"center", justifyContent:"space-between"}}>
                    <Box>Game has not started!</Box>
                    <Box>Competition will start at {getDateFormatted(roundInfo.startTime.toISOString())}</Box>
                </Box>
            }else{
                return <Box style={{display:"flex", flexDirection:"row", alignItems:"center", justifyContent:"space-between"}}>
                    <Box>Game has not started!</Box>
                    <Box>VM access at {getDateFormatted(roundInfo.startGraceTime.toISOString())}</Box>
                </Box>
            }
        }
        if (!roundInfo.hasStarted){
            return <Box style={{display:"flex", flexDirection:"row", alignItems:"center", justifyContent:"space-between"}}>
                <Box>Game will start soon...</Box>
                <Box>Now you can access your VM</Box>
            </Box>
        }
        if (roundInfo.hasEnded){
            return <Box style={{display:"flex", flexDirection:"row", alignItems:"center", justifyContent:"space-between"}}>
                <Box>Game has ended!</Box>
                <Box>The game network is locked</Box>
            </Box>
        }
        if (roundInfo.currentRound<0){
            return <Box style={{display:"flex", flexDirection:"row", alignItems:"center", justifyContent:"space-between"}}>
                <Box>Game has started!</Box>
                <Box>Next round {lastsTimeString?'in '+lastsTimeString:'soon...'}</Box>
            </Box>
        }
        return <Box style={{display:"flex", flexDirection:"row", alignItems:"center", justifyContent:"space-between"}}>
            <Box>Current Round: {roundInfo.currentRound}</Box>
            <Box>Next round {lastsTimeString?'in '+lastsTimeString:'soon...'}</Box>
        </Box>
    }

    return config.isSuccess?<Box>
        <Text size="md">{genInfoText()}</Text>
        <Progress size="lg" value={roundInfo.hasEnded ? 100 : roundInfo.hasStarted?roundInfo.currentRoundPercent:0} color="red" animated={!roundInfo.hasEnded} />
        <Box className="center-flex" mt="sm">
            <Text size="md"><Badge size="md" radius="md" color="teal" >Starts - {getDateFormatted(roundInfo.startTime.toISOString())}</Badge> </Text>
            <Box style={{flex:1}}/>
            <Text size="md"><Badge size="md" radius="md" color="teal" >Ends - {roundInfo.endTime?getDateFormatted(roundInfo.endTime?.toISOString()??""):"Will never End"}</Badge> </Text>
        </Box>
    </Box>:<Progress size="lg" color="red" value={0}/>
}