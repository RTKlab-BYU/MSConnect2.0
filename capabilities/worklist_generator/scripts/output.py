from pathlib import Path

import pandas as pd
from django.conf import settings

SINGLE_CHANNEL = 1
DUAL_CHANNEL = 2


class Output:
    def __init__(self, parser_output, blocker_output, output_dir=None):
        self.nbcode = parser_output[0]
        self.lc_number = parser_output[1]
        self.blank_method = parser_output[2]
        self.sample_type = parser_output[3]
        self.lc_symbol = parser_output[4]
        self.ms_type = parser_output[5]
        self.well_conditions = blocker_output[0]
        self.block_runs = blocker_output[1]
        self.positions = blocker_output[2]
        self.inj_vols = blocker_output[3]
        self.reps = blocker_output[4]
        self.msmethods = blocker_output[5]
        self.lcmethods = blocker_output[6]
        self.conditions = blocker_output[7]
        self.output_dir = Path(output_dir) if output_dir else None

    def create_filenames(self):
        filenames = []
        condition_names = []  # condition/group name for each filename, for SDRF generation
        rep_numbers = []      # replicate number for each filename, for SDRF generation
        tb_method_found = False

        if self.lc_number == SINGLE_CHANNEL:
            columns = [
                "nbcode",
                "conditions",
                "block and run",
                "position",
                "rep",
                "msmethod",
                "lcmethod",
            ]
        elif self.lc_number == DUAL_CHANNEL:
            columns = [
                "nbcode",
                "conditions",
                "block and run",
                "position",
                "rep",
                "channel",
                "msmethod",
                "lcmethod",
            ]

        df = pd.DataFrame(columns=columns)

        for index, _ in enumerate(self.block_runs):
            try:
                condition = self.conditions[self.well_conditions[index]][1]
            except KeyError:
                msg = (
                    f"Condition {self.well_conditions[index]} not found in conditions dictionary. "
                    f"Conditions: {list(self.conditions.keys())}"
                )
                raise KeyError(
                    msg,
                )
            if self.lc_number == SINGLE_CHANNEL:
                df.loc[len(df)] = [
                    self.nbcode,
                    condition,
                    self.block_runs[index],
                    self.positions[index],
                    f"rep{self.reps[index]}",
                    self.msmethods[index],
                    self.lcmethods[index],
                ]
            elif self.lc_number == DUAL_CHANNEL:
                df.loc[len(df)] = [
                    self.nbcode,
                    condition,
                    self.block_runs[index],
                    self.positions[index],
                    f"rep{self.reps[index]}",
                    f"ch{(index % 2) + 1}",
                    self.msmethods[index],
                    self.lcmethods[index],
                ]
                if condition == "TrueBlank":
                    tb_method = self.msmethods[index]
                    tb_method_found = True
            condition_names.append(condition)
            rep_numbers.append(self.reps[index])
        for run_num, (_, row) in enumerate(df.iterrows(), start=1):
            joined = "_".join(
                str(x).strip().replace(" ", "_") for x in row if pd.notna(x)
            )
            if self.ms_type:
                joined += f"_run{run_num}"
            filenames.append(joined)

        if tb_method_found:
            return filenames, tb_method, condition_names, rep_numbers
        return filenames, None, condition_names, rep_numbers

    def create_instrument_methods(self, methodpaths, methods, csv_file):
        inst_methods = []
        for counter, (index, path) in enumerate(enumerate(methodpaths)):
            if csv_file == "LC" and self.lc_number == DUAL_CHANNEL:
                if counter % 2 == 0:
                    methods[index] = "ChannelA_" + methods[index]
                elif counter % 2 == 1:
                    methods[index] = "ChannelB_" + methods[index]
            inst_methods.append("\\".join([path.strip(), methods[index].strip()]))
        return inst_methods

    def final_csv_format_as_pd(
        self,
        csv_file,
        filenames,
        well_conditions,
        positions,
        inj_vols,
        tb_method,
    ):
        method_paths = []
        method_names = []
        data_paths = []

        # Add position symbol for Vanquish Neo
        if self.lc_symbol:
            positions = [p[0] + self.lc_symbol + p[1:] for p in positions]

        for index in well_conditions:
            if index not in self.conditions:
                msg = f"Condition {index} not found."
                raise KeyError(msg)
            if len(self.conditions[index]) < 10:
                msg = (
                    f"Condition {index} is malformed: expected at least 10 fields, "
                    f"but got {len(self.conditions[index])}. Check the corresponding "
                    "row in your Excel sheet for missing values."
                )
                raise ValueError(
                    msg,
                )
            try:
                if csv_file == "MS":
                    data_paths.append(self.conditions[index][2].strip())
                    method_paths.append(self.conditions[index][3].strip())
                    method_names.append(self.conditions[index][5].strip())
                elif csv_file == "LC":
                    data_paths.append(self.conditions[index][6].strip())
                    method_paths.append(self.conditions[index][7].strip())
                    method_names.append(self.conditions[index][9].strip())
            except Exception:
                msg = (
                    f"Condition {index} is malformed. Make sure all additional "
                    "data for this condition is filled out."
                )
                raise ValueError(
                    msg,
                )

        inst_methods = self.create_instrument_methods(
            method_paths,
            method_names,
            csv_file,
        )

        # Offset rows for 2-column system
        if self.lc_number == DUAL_CHANNEL:
            filenames.insert(0, f"{self.nbcode}_Preblank2")
            filenames.insert(0, f"{self.nbcode}_Preblank1")
            data_paths.insert(0, data_paths[0])
            data_paths.insert(0, data_paths[0])
            if tb_method is None:
                inst_methods.append(inst_methods[-1])
                inst_methods.append(inst_methods[-1])
            else:
                inst_methods.append(tb_method)
                inst_methods.append(tb_method)
            positions.append(positions[-1])
            positions.append(positions[-1])
            inj_vols.append(1)
            inj_vols.append(1)

        if not (
            len(filenames)
            == len(data_paths)
            == len(inst_methods)
            == len(positions)
            == len(inj_vols)
        ):
            msg = "Mismatched lengths when creating CSV data."
            raise IndexError(msg)

        df = pd.DataFrame(
            {
                "Sample Type": [self.sample_type] * len(filenames),
                "File Name": filenames,
                "Path": data_paths,
                "Instrument Method": inst_methods,
                "Position": positions,
                "Inj Vol": inj_vols,
            },
        )

        data_rows = df.to_numpy().tolist()
        rows = [
            ["Bracket Type=4", "", "", "", "", ""],
            [
                "Sample Type",
                "File Name",
                "Path",
                "Instrument Method",
                "Position",
                "Inj Vol",
            ],
        ]
        rows.extend(data_rows)
        return pd.DataFrame(rows)

    def putout(self):
        filenames, tb_method, condition_names, rep_numbers = self.create_filenames()

        ms_pd = self.final_csv_format_as_pd(
            "MS",
            filenames.copy(),
            self.well_conditions.copy(),
            self.positions.copy(),
            self.inj_vols.copy(),
            tb_method,
        )
        lc_pd = self.final_csv_format_as_pd(
            "LC",
            filenames.copy(),
            self.well_conditions.copy(),
            self.positions.copy(),
            self.inj_vols.copy(),
            tb_method,
        )

        results_dir = self.output_dir or Path(settings.MEDIA_ROOT) / "worklist_generator_results"
        results_dir.mkdir(parents=True, exist_ok=True)

        ms_filename = results_dir / f"{self.nbcode}_MS.csv"
        lc_filename = results_dir / f"{self.nbcode}_LC.csv"

        ms_pd.to_csv(ms_filename, index=False, header=False, encoding="utf-8-sig")
        lc_pd.to_csv(lc_filename, index=False, header=False, encoding="utf-8-sig")

        # filenames/condition_names/rep_numbers are returned (not just used internally) so that
        # SDRF generation in stage 3 can map each raw file to its group's metadata and replicate number.
        return ms_filename, lc_filename, filenames, condition_names, rep_numbers
