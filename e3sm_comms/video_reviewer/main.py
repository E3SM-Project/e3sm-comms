import re
from datetime import datetime, timedelta
from typing import List, Tuple

INPUT_TIMESTAMPS = (
    "/home/ac.forsyth2/ez/e3sm-comms-io/input/video_reviewer/timestamps.txt"
)
INPUT_CUTS = "/home/ac.forsyth2/ez/e3sm-comms-io/input/video_reviewer/cuts.txt"
OUTPUT_UPDATED_TIMESTAMPS = (
    "/home/ac.forsyth2/ez/e3sm-comms-io/output/video_reviewer/updated_timestamps.txt"
)


def main():
    read_and_write_video_timestamps(INPUT_TIMESTAMPS, INPUT_CUTS)


def read_and_write_video_timestamps(timestamp_file: str, block_file: str):
    with open(f"{timestamp_file}", "r") as f:
        timestamp_strs: List[str] = f.readlines()
    with open(f"{block_file}", "r") as f:
        block_lines: List[str] = f.readlines()
    block_strs: List[Tuple[str, str]] = []
    for line in block_lines:
        t = tuple(line.split("-"))
        if len(t) == 2:
            block_strs.append(t)
        else:
            print(f"Warning: line {line} gives a tuple of invalid size: {t}")
    new_timestamps: List[str] = update_video_timestamps(timestamp_strs, block_strs)
    with open(OUTPUT_UPDATED_TIMESTAMPS, "w") as f:
        for ts in new_timestamps:
            f.write(ts + "\n")


def update_video_timestamps(
    timestamp_strs: List[str], block_strs: List[Tuple[str, str]]
) -> List[str]:
    timestamps: List[datetime] = list(map(convert_to_datetime, timestamp_strs))
    blocks_to_cut: List[Tuple[datetime, datetime]] = list(
        map(convert_to_datetime_tuple, block_strs)
    )
    remove_index: int = 0
    new_timestamps: List[timedelta] = []
    cumulative_time_removed: datetime = convert_to_datetime("00:00:00")
    for timestamp in timestamps:
        while (remove_index < len(blocks_to_cut)) and (
            blocks_to_cut[remove_index][0] < timestamp
        ):
            # Calculate how much time is being cut
            block_duration: timedelta = (
                blocks_to_cut[remove_index][1] - blocks_to_cut[remove_index][0]
            )
            print(f"Cutting {str(block_duration)[-8:]}")
            # Add that to the amount of time cut so far
            cumulative_time_removed += block_duration
            # We've processed this block, so we can move onto the next
            remove_index += 1
        new_timestamps.append(timestamp - cumulative_time_removed)
    print(f"Cumulative time removed={str(cumulative_time_removed)[-8:]}")
    return list(map(convert_to_str, new_timestamps))


def convert_to_datetime_tuple(
    timestamp_tuple: Tuple[str, str],
) -> Tuple[datetime, datetime]:
    return (
        convert_to_datetime(timestamp_tuple[0]),
        convert_to_datetime(timestamp_tuple[1]),
    )


# Stand-alone function
def subtract_time(time_string: str, subtraction_string: str) -> str:
    y = convert_to_datetime(time_string)
    x = convert_to_datetime(subtraction_string)
    delta = (y - x).seconds
    hour_diff = delta // 3600
    remaining_seconds = delta % 3600
    minute_diff = remaining_seconds // 60
    second_diff = remaining_seconds % 60
    return f"{hour_diff:02}:{minute_diff:02}:{second_diff:02}"


def convert_to_datetime(timestamp_str: str) -> datetime:
    re_match = re.match(r"(\d\d):(\d\d):(\d\d)", timestamp_str)
    if re_match:
        h = int(re_match.group(1))
        m = int(re_match.group(2))
        s = int(re_match.group(3))
        return datetime(2025, 1, 1, h, m, s)  # Arbitrary year, month, day
    else:
        raise ValueError(f"Malformed timestamp_str={timestamp_str}")


def convert_to_str(dt: timedelta) -> str:
    delta = dt.seconds
    hour_diff = delta // 3600
    remaining_seconds = delta % 3600
    minute_diff = remaining_seconds // 60
    second_diff = remaining_seconds % 60
    return f"{hour_diff:02}:{minute_diff:02}:{second_diff:02}"
