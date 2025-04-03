import { useEffect, useState } from "react";  

export const RainbowText = ({ text, style }: { text: string, style?: React.CSSProperties }) => {

    const [textStyle, setTextStyle] = useState<React.CSSProperties>({})
    const [memColor, setMemColor] = useState<string[]>([
        'rgba(255, 0, 0, 1)', 'rgba(255, 154, 0, 1)', 'rgba(208, 222, 33, 1)',
        'rgba(79, 220, 74, 1)', 'rgba(63, 218, 216, 1)', 'rgba(47, 201, 226, 1)',
        'rgba(28, 127, 238, 1)', 'rgba(95, 21, 242, 1)', 'rgba(186, 12, 248, 1)',
        'rgba(251, 7, 217, 1)', 'rgba(255, 0, 0, 1)'
      ])

    function changeColor() {
        
        let rainbowColors = memColor

        let nextColor = rainbowColors.shift();
        if (nextColor) rainbowColors.push(nextColor);
        setTextStyle({
            WebkitTextFillColor: "transparent",
            WebkitBackgroundClip: "text",
            backgroundImage: `linear-gradient(-45deg, ${rainbowColors.join(', ')})`,
            animation: "rainbow 6s linear infinite"
        })
        setMemColor(rainbowColors)
    }

    useEffect(()=>{
        const interval = setInterval(changeColor, 80)
        return () => clearInterval(interval)
    }, [])

    return <span style={{...textStyle, ...style}}>{text}</span>
}