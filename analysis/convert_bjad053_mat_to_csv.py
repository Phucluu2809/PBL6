import csv
import re
from pathlib import Path

from mat4py import loadmat


SOURCE = Path("data/bjad053_suppl_Supplementary_Data.mat")
OUTPUT_DIR = Path("data/bjad053_csv")
SENSORS = ["W1C", "W5S", "W3C", "W6S", "W5C", "W1S", "W1W", "W2S", "W2W", "W3S"]
SENSOR_DESCRIPTIONS = {
    "W1C": "Aromatic organic compounds",
    "W5S": "Broad sensitivity; nitrogen oxides; negative signal",
    "W3C": "Ammonia and aromatic compounds",
    "W6S": "Mainly hydrogen",
    "W5C": "Alkanes, aromatic and nonpolar organic compounds",
    "W1S": "Methane and broad range of organic compounds",
    "W1W": "Inorganic sulfur, terpenes and sulfur-containing organic compounds",
    "W2S": "Alcohol and aromatic compounds; broad sensitivity",
    "W2W": "Aromatic, inorganic sulfur and organic compounds",
    "W3S": "High concentrations of methane and aliphatic organic compounds",
}
FILENAME_PATTERN = re.compile(
    r"^(?P<participant>[MW]\d+)_(?P<date>\d{8})_(?P<sample_type>.+)_"
    r"(?P<replicate>\d+)_(?P<device>Enose\d+)\.nos$"
)


def parse_filename(filename):
    match = FILENAME_PATTERN.match(filename)
    if not match:
        raise ValueError(f"Unexpected filename format: {filename}")
    fields = match.groupdict()
    raw_date = fields["date"]
    fields["date"] = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
    fields["sex"] = {"M": "male", "W": "female"}[fields["participant"][0]]
    fields["replicate"] = int(fields["replicate"])
    return fields


def write_records(dataset):
    metadata_fields = list(next(item for item in dataset["info"] if isinstance(item, dict)))
    fieldnames = [
        "record_id",
        "filename",
        "participant",
        "sex",
        "date",
        "sample_type",
        "replicate",
        "device",
        "time_of_day_raw",
        *metadata_fields,
        *(f"endpoint_{sensor}" for sensor in SENSORS),
    ]

    with (OUTPUT_DIR / "records.csv").open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for index, filename in enumerate(dataset["filename"]):
            row = {
                "record_id": index + 1,
                "filename": filename,
                **parse_filename(filename),
                "time_of_day_raw": dataset["TimeOfDay"][index],
            }
            info = dataset["info"][index]
            if isinstance(info, dict):
                row.update(info)
            row.update(
                {
                    f"endpoint_{sensor}": value
                    for sensor, value in zip(SENSORS, dataset["EndptsVector"][index])
                }
            )
            writer.writerow(row)


def write_timeseries(dataset):
    fieldnames = [
        "record_id",
        "filename",
        "measurement_second",
        *(f"sensor_{sensor}" for sensor in SENSORS),
    ]
    with (OUTPUT_DIR / "timeseries.csv").open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.writer(output)
        writer.writerow(fieldnames)
        for index, (filename, measurements) in enumerate(zip(dataset["filename"], dataset["data"])):
            for second, sensor_values in enumerate(measurements, start=1):
                writer.writerow([index + 1, filename, second, *sensor_values])


def write_sensor_dictionary():
    with (OUTPUT_DIR / "sensor_dictionary.csv").open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.writer(output)
        writer.writerow(["sensor_number", "sensor_name", "general_description"])
        for number, sensor in enumerate(SENSORS, start=1):
            writer.writerow([number, sensor, SENSOR_DESCRIPTIONS[sensor]])


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = loadmat(str(SOURCE))["OsmOzen_Data_Matlab_full"]
    write_records(dataset)
    write_timeseries(dataset)
    write_sensor_dictionary()
    print(f"Wrote CSV files to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
