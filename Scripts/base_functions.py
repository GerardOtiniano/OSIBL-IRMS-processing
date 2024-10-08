import pandas as pd
from datetime import datetime, timedelta
import time
import os
import numpy as np
from matplotlib.dates import date2num
from queries import *


def make_correction_df():
    correction_log_data = {
        "type": ["Drift", "Linearity", "VSMOW", "Methylation"],
        "sample": [0, 0, 0, 0],  # Default values
    }
    correction_log = pd.DataFrame(correction_log_data)
    correction_log = correction_log.set_index(["type"])
    return correction_log


def try_parse_date(date_str):
    # List of date formats to try
    formats = ["%m/%d/%Y %H:%M:%S", "%m/%d/%y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None  # Return None if all formats fail


def create_log_file(folder_path):
    """
    Create log file.
    """
    # Ensure the folder exists
    os.makedirs(folder_path, exist_ok=True)
    # Create the full path for the log file
    log_file_path = os.path.join(folder_path, "Log file.txt")
    # Create the log file and write the initial message
    with open(log_file_path, "w") as log_file:
        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        initial_message = "Log file created at " + str(current_datetime) + "\n"
        log_file.write(initial_message)
    return log_file_path


def append_to_log(log_file_path, log_message):
    """
    Add entry to log file.
    """
    with open(log_file_path, "a") as log_file:
        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        initial_message = f"Log file created at {current_datetime}\n"
        log_file.write(log_message + "; " + str(current_datetime) + "\n")


def import_data(data_location, folder_path, log_file_path, isotope):
    """
    Import .csv file from GCIRMs - default .csv file from GCIRMS creates issues with header. The function assigns new header names,
    creates a date-time format for linear regression, identifieds standards, and isolates standards and samples.
    Outputs:
        df             - original dataframe
        linearirty_std - dataframe with linearity standards
        drif_std       - dataframe with drift standards
        unknown        - dataframe with sample data
    ~GAO~ 12/4/2023
    """
    # Create log file

    df = pd.read_csv(data_location)
    new_name = [str(isotope), "area", "chain"]
    x = 0
    if isotope == "dD":
        iso_rat = "d 2H/1H"
    if isotope == "dC":
        iso_rat = "d 13C/12C"
    for name in [str(iso_rat), "Area All", "Component"]:
        if name in df.columns:
            df = df.rename(columns={df.columns[df.columns.str.contains(name)][0]: new_name[x]})
            x = x + 1
        else:
            print(name)
            df[name] = pd.NA
    # df['date-time_true'] = pd.to_datetime(df['Date'] + ' ' + df['Time'], format='%m/%d/%y %H:%M:%S')
    df["date-time_true"] = df.apply(lambda row: try_parse_date(row["Date"] + " " + row["Time"]), axis=1)
    df["date-time"] = date2num(df["date-time_true"])
    df["time_rel"] = df["date-time"] - df["date-time"].max()

    # Seperate samples, H3+, drift, and linearity standards
    linearity_std = df[df["Identifier 1"].str.contains("C20") & df["Identifier 1"].str.contains("C28")]  # Isolate linearity standards
    linearity_std = linearity_std[linearity_std.chain.isin(["C20", "C28"])]
    append_to_log(log_file_path, "Number of linearity standards analyzed: " + str(len(linearity_std[linearity_std.chain == "C28"])))

    drift_std = df[df["Identifier 1"].str.contains("C18") & df["Identifier 1"].str.contains("C24")]  # Isolate drift standards
    drift_std = drift_std[drift_std.chain.isin(["C18", "C24"])]
    append_to_log(log_file_path, "Number of Drift standards analyzed: " + str(len(drift_std[drift_std.chain == "C24"])))

    # Remove first two drift runs
    drift_std = drift_std.sort_values("date-time_true")
    unique_time_signatures = drift_std["date-time"].unique()  # identify unique drift runs
    # time_signatures_to_remove = unique_time_signatures[6:] # find time signature of first two runs
    time_signatures_to_remove = unique_time_signatures[:2]  # Modified Jan 7, 2024 - line above is original method, but didnt work?
    drift_std = drift_std[~drift_std["date-time"].isin(time_signatures_to_remove)]  # Remove first two runs - OSIBL ignores for variance
    append_to_log(log_file_path, "First two drift standards ignored.")
    mask = df["Identifier 1"].str.contains("C18") & df["Identifier 1"].str.contains("C24")
    unknown = df[~mask]
    mask = unknown["Identifier 1"].str.contains("C20") & unknown["Identifier 1"].str.contains("C28")
    unknown = unknown[~mask]
    unknown = unknown[~unknown["Identifier 1"].str.contains("H3+")]
    rt_dict = ask_user_for_rt(log_file_path)
    if rt_dict:
        unknown = process_dataframe(unknown, rt_dict, folder_path)
        unknown = unknown[unknown.chain != "None"]
        linearity_std = process_dataframe(linearity_std, rt_dict, folder_path)
        drift_std = process_dataframe(drift_std, rt_dict, folder_path)
    else:
        unknown = unknown[unknown.chain.isin(["C16", "C18", "C20", "C22", "C24", "C24", "C26", "C28", "C30", "C32"])]
    for i in [unknown, drift_std, linearity_std]:
        i = i[~i.chain.isna()]
    correction_log = make_correction_df()
    return linearity_std, drift_std, unknown, correction_log


def create_folder(name, isotope, dir=os.getcwd()):
    folder_path = os.path.join(dir, name)
    log_file_path = create_log_file(folder_path)
    if isotope == "dD":
        iso_name = "δD"
    else:
        iso_name = "δC"
    append_to_log(log_file_path, "Isotope type: " + str(iso_name))
    os.makedirs(folder_path, exist_ok=True)

    # Make output folders
    fig_path = os.path.join(folder_path, "Figures")
    os.makedirs(fig_path, exist_ok=True)

    results_path = os.path.join(folder_path, "Results")
    os.makedirs(results_path, exist_ok=True)

    locate = query_file_location()  # Location of file

    return folder_path, fig_path, results_path, locate, log_file_path


def create_subfolder(folder_path, name):
    subf_path = os.path.join(folder_path, name)
    os.makedirs(subf_path, exist_ok=True)
    return subf_path


def closest_rt(df, time_val, target_rt, threshold=0.05):
    """
    Find the closest retention time(s) to the target.
    If two values are almost equally close (within a threshold), return both.
    """
    sample_df = df[df["Time"] == time_val]
    differences = (sample_df["Rt"] - target_rt).abs()
    min_diff = differences.min()
    closest_rows = sample_df[differences <= min_diff * (1 + threshold)]
    return closest_rows


def ask_user_for_rt(log_file_path):
    chain_lengths = ["C16", "C18", "C20", "C22", "C24", "C26", "C28", "C30", "C32"]
    while True:
        response = input("Do you want to detect components in this dataset by retention time? (Y/N):\n").strip().lower()
        if pos_response(response):
            append_to_log(log_file_path, "User opted to identify chains.")
            rt_values = input("Enter retention times for " + ", ".join(chain_lengths) + " separated by commas (type 'none' for any you don't want to use):\n")
            rt_values = rt_values.split(",")
            if len(rt_values) == len(chain_lengths):
                rt_dict = {chain: (None if rt.strip().lower() == "none" else float(rt.strip())) for chain, rt in zip(chain_lengths, rt_values)}
                return rt_dict
            else:
                print("Invalid input. Please provide the correct number of values.\n")
        elif neg_response(response):
            append_to_log(log_file_path, "User opted not to identify chains.")
            print("Component detection not selected.\n")
            return None
        else:
            print("Invalid response. Please answer 'yes' or 'no'.\n")


def process_dataframe(df, rt_dict, folder_path, log_file_path):
    if rt_dict is None:
        return df
    rt_path = create_subfolder(folder_path, "Retention time figures")
    df["chain"] = None
    unique_times = df["Time"].unique()
    for time_val in unique_times:
        sample_id = df.loc[df["Time"] == time_val, "Identifier 1"].iloc[0]

        # For 'standard' types, use chains mentioned in Identifier 1 or all chains if none are mentioned
        filtered_rt_dict = rt_dict
        for chain, rt in filtered_rt_dict.items():
            if rt is not None:
                closest_rows = closest_rt(df, time_val, rt)
                if len(closest_rows) == 1:
                    # Only one clear closest match
                    correct_rt = closest_rows.iloc[0]["Rt"]
                    df.loc[(df["Time"] == time_val) & (df["Rt"] == correct_rt), "chain"] = chain
                elif len(closest_rows) > 1:
                    # Two closely matched peaks, prompt the user
                    clear_output(wait=True)
                    plt.figure()
                    sample_df = df[df["Time"] == time_val]
                    plt.scatter(sample_df["Rt"], sample_df["Area All"], label=sample_id, color="red", ec="k")
                    plt.plot(sample_df["Rt"], sample_df["Area All"], label=sample_id, linestyle="--", c="k")
                    x = 0
                    lim = -999
                    for index, (_, row) in enumerate(closest_rows.iterrows(), start=1):
                        if x == 0:
                            lim = row["Rt"]
                        plt.axvline(x=row["Rt"], color="red", linestyle="--", alpha=0.5)
                        plt.text(row["Rt"], sample_df["Area All"].mean() + x, str(index), color="k", fontsize=12, verticalalignment="bottom")
                        x = x + 5
                    plt.xlabel("Retention Time")
                    plt.ylabel("Area")
                    plt.title(f"Close Matches for {sample_id} ({time_val}) - {chain}")
                    if lim != -999:
                        if lim > row["Rt"]:
                            x_min = row["Rt"] - 50
                            x_max = lim + 50
                        else:
                            x_min = lim - 50
                            x_max = row["Rt"] + 50
                    else:
                        x_min = 450
                        x_max = row["Rt"] + 50
                    plt.xlim(x_min, x_max)
                    plt.legend()
                    plt.savefig(os.path.join(rt_path, "Sample " + str(sample_id) + "Chain " + str(chain) + " rt " + str(rt) + ".png"), dpi=300, bbox_inches="tight")
                    plt.show()

                    choice = input(f"Enter the number associated with the correct retention time for {chain} in sample {sample_id} ({time_val}), or type 'none' to skip:\n").strip().lower()
                    if choice == "none":
                        continue
                    choice = int(choice)
                    correct_rt = closest_rows.iloc[choice - 1]["Rt"]
                    df.loc[(df["Time"] == time_val) & (df["Rt"] == correct_rt), "chain"] = chain
                else:
                    df.loc[closest_rows.index, "chain"] = chain
    export_df = df[df["chain"].isin(["C16", "C18", "C20", "C22", "C24", "C26", "C28", "C30", "C32"])]
    append_to_log(log_file_path, f"Chain lengths identified by user: {export_df.chain.unique()}")
    return export_df
