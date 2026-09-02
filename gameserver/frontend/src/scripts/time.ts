
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import duration, { Duration } from 'dayjs/plugin/duration';
import relativeTime from 'dayjs/plugin/relativeTime';


dayjs.extend(utc);
dayjs.extend(duration);
dayjs.extend(relativeTime);

export const durationToString = (duration: Duration): string => {
    let result = []
    
    if (duration.years() > 0) {
        result.push(`${duration.years()} years`)
    }
    if (duration.months() > 0) {
        result.push(`${duration.months()} month`)
    }
    if (duration.days() > 0) {
        result.push(`${duration.days()} days`)
    }
    if (duration.hours() > 0) {
        result.push(`${duration.hours()} h`)
    }
    if (duration.minutes() > 0) {
        result.push(`${duration.minutes()} m`)
    }
    if (duration.seconds() > 0) {
        result.push(`${duration.seconds()} s`)
    }
    // Anything under a second has no whole component to show, and an empty
    // string reads as a bug ("1 / " with nothing after it). Say the
    // milliseconds instead, and call a zero duration what it is.
    if (result.length === 0) {
        const millis = Math.round(duration.asMilliseconds())
        return millis > 0 ? `${millis} ms` : "0 s"
    }
    return result.join(", ")
}

export const secondDurationToString = (duration: number): string => {
    return durationToString(dayjs.duration(duration, "s"))
}

export const getDeltaDurationTextFromNow = (lastUpdate:string|null) => {
    if(!lastUpdate) return "never"
    return durationToString(dayjs.duration(dayjs.utc().diff(dayjs.utc(lastUpdate)))) + " ago";
}

export const getDateFormatted = (date:string) => {
    return dayjs(getLocalizedISO((date))).format("DD/MM/YYYY HH:mm:ss")
}

export const getDateSmallFormatted = (date:string) => {
    return dayjs(getLocalizedISO((date))).format("DD/MM HH:mm:ss")
}

export const getLocalizedISO = (date:string) => {
    return dayjs.utc(date).local().toISOString()
}