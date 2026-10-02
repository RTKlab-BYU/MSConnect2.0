import math
import random
import re
import sys
from collections import Counter
from collections import defaultdict

import numpy as np
import pandas as pd

SOLVENT_VIAL_LIMIT = 999
SINGLE_CHANNEL = 1
DUAL_CHANNEL = 2


class Blocker:
    def __init__(self, parser_output):
        self.user_df = parser_output[0]
        self.manager_df = parser_output[1]
        self.lc_number = parser_output[2]
        self.all_conditions = parser_output[3][0]
        self.conditions1 = parser_output[3][1] if len(parser_output[3]) > 1 else None
        self.conditions2 = parser_output[3][2] if len(parser_output[3]) > 2 else None
        self.wet_amounts = parser_output[4]
        self.plates = parser_output[5]
        self.solvent_vials = parser_output[6]
        self.num_to_run = parser_output[7]
        self.lib_placement = parser_output[8]
        self.sysvalid_interval = parser_output[9]
        self.tb_location = parser_output[10]
        self.cond_range1 = parser_output[11]
        self.cond_range2 = parser_output[12]
        self.lib_same = parser_output[13]
        self.even = parser_output[14]
        self.qc_frequency = parser_output[15]
        self.inj_vol = parser_output[16]
        self.run_seed = parser_output[17] if len(parser_output) > 17 else None

        self.generate_seed(self.run_seed) # Set the random seed for reproducibility


    def generate_seed(self, run_seed=None):
        # Prioritize an explicitly passed argument, then the instance seed, then a random integer
        chosen_seed = run_seed if run_seed is not None else self.run_seed
        if chosen_seed is None:
            chosen_seed = random.randrange(sys.maxsize)
        random.seed(chosen_seed)
        print(f"Random seed set to: {chosen_seed}")
        
    def safe_int(self, val, default=0):
        try:
            if pd.isna(val):
                return default
            return int(val)
        except (ValueError, TypeError):
            return default

    def check_for_trueblank(self, conditions1, conditions2=None):
        for i, (key_num, v) in enumerate(conditions1.items()):
            if v[0] == "TrueBlank":
                # raise ValueError(f"check key value: {key_num}\n check v: {v}")
                # changed second return from "i+1" to key_num. This fixes a problem with the trueblank condition if there are gaps between conditions in the excel sheet.
                return (
                    (conditions1, key_num, True)
                    if not conditions2
                    else (conditions1, conditions2, key_num + 1, True)
                )
        if conditions2:
            for i, (key_num, v) in enumerate(conditions2.items()):
                if v[0] == "TrueBlank":
                    return conditions1, conditions2, i + 1, True
        conditions1[100] = [
            "TrueBlank",
            "TrueBlank",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            0,
            0,
            0,
            0,
            0,
            0,
        ]  # assign trueblank a high number to keep it at the end if it's not already in conditions
        return (
            (conditions1, 100, False)
            if not conditions2
            else (conditions1, conditions2, 100, False)
        )

    def check_for_sysvalid(self, conditions):
        sys_valid_cond = {}
        for i, (_, v) in enumerate(conditions.items()):
            if v[0] == "SystemValidation":
                sys_valid_cond[i + 1] = v
                return sys_valid_cond, i + 1, True
        return None, 0, False

    def parse_range(self, cond_range):
        if (
            cond_range is None
            or (isinstance(cond_range, float) and np.isnan(cond_range))
            or str(cond_range).strip() == ""
        ):
            return [0, 0]  # treat blank as no conditions
        s = str(cond_range).strip()
        # Try number-number
        matches = re.findall(r"(\d+)-(\d+)", s)
        if matches:
            start, end = map(int, matches[0])
            return [start, end]
        msg = f"Invalid condition range: {cond_range!r}"
        raise ValueError(msg)

    def process_plate(self, plate, plate_name, wet_amounts, cond_range=None):
        wells_list = []
        RGBY = plate_name.split("_")[0]
        if cond_range:
            try:
                ranges = self.parse_range(cond_range)
            except TypeError:
                ranges = [
                    "0",
                    "0",
                ]  # range was defined as blank so conditions should return blank
        # newplate = plate.iloc[int(ranges[0]):int(ranges[1])+1, :].copy()
        for r_idx, row_series in plate.iterrows():
            for col_name in plate.columns:
                try:
                    col_num = int(col_name)
                except ValueError as err:
                    msg = f"Column name '{col_name}' in plate '{plate_name}' must be a unique integer (e.g., 1, 2, 3). Please rename the column accordingly."
                    raise ValueError(msg) from err
                value = row_series.loc[col_name]
                if pd.isna(value):
                    continue
                plate_location = f"{r_idx}{col_num}"  # well location (e.g. A1)
                abs_location = RGBY + plate_location
                try:
                    try:
                        # Try to coerce to float first, whether it's a number or a numeric string
                        as_float = float(value)
                        if math.isfinite(as_float) and as_float.is_integer():
                            normalized_value = int(as_float)
                        else:
                            raise ValueError
                    except (ValueError, TypeError):
                        msg = (
                            f"Invalid condition ID '{value}' at location {abs_location}. "
                            "Condition IDs must be whole numbers without extra symbols."
                        )
                        raise ValueError(
                            msg,
                        )
                    for _ in range(int(wet_amounts[normalized_value])):
                        if cond_range:
                            if normalized_value in range(
                                int(ranges[0]),
                                int(ranges[1]) + 1,
                            ):
                                wells_list.append(
                                    [normalized_value, abs_location],
                                )  # value, absolute location (e.g. RA1)
                        else:
                            wells_list.append(
                                [normalized_value, abs_location],
                            )  # value, absolute location (e.g. RA1)
                except KeyError:
                    if cond_range:
                        continue  # only adds wells to wells_list associated with the conditions specified in cond_range
                    msg = "ERROR: You may have a sample in your plate that is not labeled in the conditions legend."
                    raise KeyError(
                        msg,
                    )
        return wells_list

    def process_solvent_vials(
        self,
        solvent_data,
        plate_name,
        wet_amounts,
        cond_range=None,
    ):
        wells_list = []
        RGBY = plate_name.split("_")[0]
        if cond_range:
            try:
                ranges = self.parse_range(cond_range)
            except TypeError:
                ranges = ["0", "0"]
        for vial_num, vial_val in solvent_data.items():
            plate_location = f"{vial_num}"
            abs_location = RGBY + plate_location
            try:
                as_float = float(vial_val)
                if math.isfinite(as_float) and as_float.is_integer():
                    normalized_value = int(as_float)
                else:
                    raise ValueError
            except (ValueError, TypeError):
                msg = (
                    f"Invalid condition ID '{vial_val}' for solvent vial {vial_num} in plate '{plate_name}'. "
                    "Condition IDs must be whole numbers without extra symbols."
                )
                raise ValueError(
                    msg,
                )
            try:
                for _ in range(SOLVENT_VIAL_LIMIT):
                    if cond_range:
                        if normalized_value in range(
                            int(ranges[0]),
                            int(ranges[1]) + 1,
                        ):
                            wells_list.append([normalized_value, abs_location])
                    else:
                        wells_list.append([normalized_value, abs_location])
            except KeyError:
                if cond_range:
                    continue
                msg = f"ERROR: Solvent vial {vial_num} in plate {plate_name} has a condition ID not found in the conditions legend."
                raise KeyError(
                    msg,
                )
        return wells_list

    def compare_wells_and_counts(self, wells_list, conditions, wet_amounts):
        if wet_amounts is None:
            msg = "Samples/well must be provided for validation"
            raise ValueError(msg)

        qc_num, wet_qc_num, blank_num, trueblank_num, Lib_num, sysvalid_num = (
            [],
            [],
            [],
            [],
            [],
            [],
        )

        # Assign condition IDs to the right bucket
        for key, row in conditions.items():
            label = row[0]
            try:
                key_int = int(key)
            except (ValueError, TypeError):
                continue  # skip malformed keys

            if label == "QC":
                qc_num.append(key_int)
            elif label == "WetQC":
                wet_qc_num.append(key_int)
            elif label == "Blank":
                blank_num.append(key_int)
            elif label == "TrueBlank":
                trueblank_num.append(key_int)
            elif label == "Library":
                Lib_num.append(key_int)
            elif label == "SystemValidation":
                sysvalid_num.append(key_int)

        # Count how many wells we actually have for each condition type
        total_QC = sum(1 for w in wells_list if w[0] in qc_num)
        total_wet_QC = sum(1 for w in wells_list if w[0] in wet_qc_num)
        total_Blank = sum(1 for w in wells_list if w[0] in blank_num)
        total_trueblank = sum(1 for w in wells_list if w[0] in trueblank_num)
        total_Lib = sum(1 for w in wells_list if w[0] in Lib_num)
        total_sysvalid = sum(1 for w in wells_list if w[0] in sysvalid_num)

        # Helper to safely extract spacing values (before/after/between)
        def spacing_sum(cond_row):
            vals = []
            for idx in (10, 11, 12):
                try:
                    vals.append(
                        int(cond_row[idx])
                        if cond_row[idx] not in (None, "", "NaN")
                        else 0,
                    )
                except (IndexError, ValueError, TypeError):
                    vals.append(0)
            return sum(vals)

        # Validator: check actual wells * wet_amounts vs expected spacings
        def validate(cond_ids, total_count, label, infinite_source=False):
            for num in cond_ids:
                expected = spacing_sum(conditions[num])
                actual = total_count * wet_amounts.get(num, 1)

                if infinite_source:
                    # Only need at least 1, no matter how many times it's referenced
                    if total_count < 1:
                        msg = f"Error: No {label} wells found, need at least 1."
                        raise ValueError(
                            msg,
                        )
                elif actual < expected:
                    msg = (
                        f"Error: Not enough {label} wells. "
                        f"Expected at least {expected}, but found {actual}."
                    )
                    raise ValueError(
                        msg,
                    )

        # Run checks for each type
        validate(qc_num, total_QC, "QC")
        validate(wet_qc_num, total_wet_QC, "WetQC")
        validate(blank_num, total_Blank, "Blank")
        validate(trueblank_num, total_trueblank, "TrueBlank", infinite_source=True)
        validate(Lib_num, total_Lib, "Library", infinite_source=True)
        validate(sysvalid_num, total_sysvalid, "SystemValidation", infinite_source=True)

    def column_sorter(
        self,
        wells_list,
        conditions,
        num_to_run,
        lc_number,
        lib_placement,
        cond_range1,
        found_tb,
        two_xp_tb,
        found_sysvalid=False,
        sysvalid_condition=None,
    ):
        column1, column2, extras = (
            [],
            [],
            [],
        )  # these are the odds ones out to attach at the end to run anyways if wanted
        nonsample_before, nonsample_after, nonsample_other = [], [], []
        qc_num, wet_qc_num, blank_num, trueblank_num, Lib_num, sysvalid_num = (
            [],
            [],
            [],
            [],
            [],
            [],
        )

        # find number associated with each nonsample well type
        for key in list(conditions.keys()):
            if conditions[key][0] == "QC":
                qc_num.append(int(key))
            if conditions[key][0] == "WetQC":
                wet_qc_num.append(int(key))
            if conditions[key][0] == "Blank":
                blank_num.append(int(key))
            if (
                conditions[key][0] == "TrueBlank" and key != 100
            ):  # if trueblank wasn't originally in conditions, it was assigned 100 so it can be sorted but not treated as a real trueblank in the blocking
                trueblank_num.append(int(key))
            if conditions[key][0] == "Library":
                Lib_num.append(int(key))

        for key in list(self.all_conditions.keys()):
            if self.all_conditions[key][0] == "SystemValidation":
                sysvalid_num.append(int(key))

        # remove non sample wells into new list
        qc_list, wet_qc_list, blank_list, trueblank_list, Lib_list, sysvalid_list = (
            [],
            [],
            [],
            [],
            [],
            [],
        )

        def extract_and_remove(wells_list, allowed_numbers, target_list):
            i = 0
            while i < len(wells_list):
                well = wells_list[i]
                if well[0] in allowed_numbers:
                    target_list.append(well)
                    wells_list.pop(i)
                else:
                    i += 1

        extract_and_remove(wells_list, set(qc_num), qc_list)
        extract_and_remove(wells_list, set(wet_qc_num), wet_qc_list)
        extract_and_remove(wells_list, set(blank_num), blank_list)
        extract_and_remove(wells_list, set(trueblank_num), trueblank_list)
        extract_and_remove(wells_list, set(Lib_num), Lib_list)
        extract_and_remove(wells_list, set(sysvalid_num), sysvalid_list)

        # randomize the nonsamples
        random.shuffle(qc_list)
        random.shuffle(wet_qc_list)
        random.shuffle(blank_list)
        random.shuffle(trueblank_list)
        random.shuffle(Lib_list)  # future: add option for nonrandomization

        if len(Lib_list) > self.sysvalid_interval - 1:
            pass

        # move a well to 'extras' if a list has an odd number of wells and it uses a 2 column system
        if lc_number == DUAL_CHANNEL:
            for lst in [qc_list, wet_qc_list, blank_list, Lib_list]:
                if len(lst) % 2:
                    extras.append(lst[-1:])
                    lst[:] = lst[:-1]

        # divide them into their respective nonsample lists based on user inputs
        def split_nonsample_list(
            nonsample_list,
            condition_numbers,
            conditions,
            before_list,
            after_list,
            other_list,
        ):
            for cond in condition_numbers:
                group = [w for w in nonsample_list if w[0] == cond]
                if not group:
                    continue
                n_before = self.safe_int(conditions[cond][10], default=0)
                n_after = self.safe_int(conditions[cond][11], default=0)

                before_slice = group[:n_before]
                remaining = group[n_before:]
                after_slice = remaining[:n_after]
                other_slice = remaining[n_after:]

                if before_slice:
                    before_list.append(before_slice)
                if after_slice:
                    after_list.append(after_slice)
                if other_slice:
                    other_list.extend(other_slice)

        split_nonsample_list(
            qc_list,
            qc_num,
            conditions,
            nonsample_before,
            nonsample_after,
            nonsample_other,
        )
        split_nonsample_list(
            wet_qc_list,
            wet_qc_num,
            conditions,
            nonsample_before,
            nonsample_after,
            nonsample_other,
        )
        split_nonsample_list(
            blank_list,
            blank_num,
            conditions,
            nonsample_before,
            nonsample_after,
            nonsample_other,
        )
        split_nonsample_list(
            trueblank_list,
            trueblank_num,
            conditions,
            nonsample_before,
            nonsample_after,
            nonsample_other,
        )
        nonsample_other = (
            nonsample_other[:10000] if len(nonsample_other) > 10000 else nonsample_other
        )

        if (
            Lib_list
            and lib_placement.upper() == "BEFORE"
            and cond_range1.upper() == "ALL"
        ):  # controls library placement
            nonsample_before.append(Lib_list)
            nonsample_before.append([[two_xp_tb, self.tb_location]] * 2)

        if (
            Lib_list
            and lib_placement.upper() == "AFTER"
            and cond_range1.upper() == "ALL"
        ):  # controls library placement
            nonsample_after.append(Lib_list)
            nonsample_after.append([[two_xp_tb, self.tb_location]] * 2)

        # if library runs are not the same in a two experiment plate, they must be returned separately
        library = []
        if Lib_list and cond_range1.upper() != "ALL":
            library.append(Lib_list)

        excluded = set(
            qc_num + wet_qc_num + blank_num + trueblank_num + Lib_num + sysvalid_num,
        )
        sample_groups = defaultdict(list)
        for well in wells_list:
            k = well[0]
            if k not in excluded and k != 100:
                sample_groups[k].append(well)

        def add_to_columns(wells):
            if lc_number == DUAL_CHANNEL:
                if len(wells) % 2:
                    extras.append(wells[-1:])
                    wells = wells[:-1]
                even = True
                for w in wells:
                    (column1 if even else column2).append(w)
                    even = not even
            else:
                column1.extend(wells)

        for sample, wells in sample_groups.items():
            random.shuffle(wells)
            max_run = num_to_run.get(sample)
            if isinstance(max_run, int):
                wells = wells[:max_run]
            add_to_columns(wells)

        if lc_number == DUAL_CHANNEL:
            return (
                nonsample_before,
                nonsample_after,
                nonsample_other,
                column1,
                column2,
                sysvalid_list,
                library,
            )

        if lc_number == SINGLE_CHANNEL:
            return (
                nonsample_before,
                nonsample_after,
                nonsample_other,
                column1,
                sysvalid_list,
                library,
            )
        return None

    def blocker(self, conditions, even, column1, column2=None):
        columns = [column1] if column2 is None else [column1, column2]
        both_blocks = []
        extras_dict = {}

        for column in columns:
            counts = Counter(well[0] for well in column)
            if not counts:
                return [[[]]], 0

            sample_block_num = min(counts.values())
            grouped = {}
            for well in column:
                grouped.setdefault(well[0], []).append(well)

            sample_dict = {
                sample: [
                    conditions[sample],
                    1 if even.upper() == "YES" else total // sample_block_num,
                    total,
                ]
                for sample, total in counts.items()
            }

            sample_blocks = []
            for _ in range(sample_block_num):
                block = []
                for sample, (_, per_block, _) in sample_dict.items():
                    if per_block > 0:
                        wells = grouped[sample][:per_block]
                        block.extend(wells)
                        grouped[sample] = grouped[sample][per_block:]
                random.shuffle(block)
                sample_blocks.append(block)

            if even.upper() == "NO":
                for sample in sample_dict:
                    leftovers = grouped.get(sample, [])
                    if not leftovers:
                        continue
                    if column is column1:
                        for well in leftovers:
                            pos = random.randint(0, len(sample_blocks) - 1)
                            sample_blocks[pos].append(well)
                            extras_dict.setdefault(well[0], [0, []])
                            extras_dict[well[0]][0] += 1
                            extras_dict[well[0]][1].append(pos)
                    else:
                        if sample not in extras_dict:
                            continue
                        placements = extras_dict[sample][1]
                        for i, well in enumerate(leftovers):
                            if i < len(placements):
                                pos = placements[i]
                                sample_blocks[pos].append(well)
                                extras_dict[sample][0] -= 1

            for block in sample_blocks:
                random.shuffle(block)

            both_blocks.append(sample_blocks)

        num_of_blocks = len(both_blocks[0]) if both_blocks else 0
        return both_blocks, num_of_blocks

    def nonsample_blocker(
        self,
        lc_number,
        nonsample_other,
        num_of_blocks,
        conditions,
        total_wells,
    ):
        """Will divide the QC, Blanks, Trueblanks etc, reserved to be between the runs, into blocks
        Make sure that number of nonsample blocks does not exceed number of sample blocks
        These blocks should not be randomized"""

        # nonsample_other = [item for block in nonsample_other for item in block] # flattens list
        sample_dict = {}
        for well in nonsample_other:
            if well[0] not in sample_dict:
                sample_dict[well[0]] = 1
            elif well[0] in sample_dict:
                sample_dict[well[0]] += 1

        sample_amounts = list(sample_dict.values())
        if sample_amounts:
            if lc_number == DUAL_CHANNEL:
                nonsample_block_num = min(sample_amounts) // 2
            elif lc_number == SINGLE_CHANNEL:
                nonsample_block_num = min(sample_amounts)
        else:
            nonsample_block_num = 0

        block_num = min([nonsample_block_num, (total_wells // self.qc_frequency)])

        for sample in list(sample_dict.keys()):
            # Count number of sample wells in wells list
            count = 0
            for well in nonsample_other:
                if well[0] == sample:
                    count += 1
            to_add = count // block_num
            if to_add == 1 and lc_number == DUAL_CHANNEL:
                msg = (
                    "If you want to include nonsample wells between sample/condition wells "
                    "in a two-column layout, "
                    "you must include at least two of each nonsample well type.")
                raise ValueError(
                    msg,
                )
            sample_dict[sample] = [conditions[sample], to_add, count]
        nonsample_blocks = []
        blocks_created = 0
        while blocks_created < block_num:
            block = []  # create each block for the samples
            for sample in sample_dict:  # go through each sample, create temporary list
                sample_list = []
                for well in nonsample_other:
                    if well[0] == sample:
                        sample_list.append(well)
                # block.append(sample_list[:sample_dict[sample][1]]) # problem?
                wells_to_append = sample_list[: sample_dict[sample][1]]
                for well in wells_to_append:
                    block.append(well)
            for item in block:
                if item in nonsample_other:
                    nonsample_other.remove(item)
            # random.shuffle(block)
            nonsample_blocks.append(block)
            blocks_created += 1
        if blocks_created == block_num and self.even.upper() == "NO":
            # assigns leftover samples randomly to blocks
            num_of_blocks = len(nonsample_blocks)
            for sample in sample_dict:  # go through each sample, create temporary list
                sample_list = []
                for well in nonsample_other:
                    if well[0] == sample:
                        sample_list.append(well)
                for item in sample_list:
                    placement = random.randint(0, num_of_blocks - 1) # noqa: S311
                    nonsample_blocks[placement].append(item)

        return nonsample_blocks

    def zipper(self, both_blocks):  # zips column1 and column2 together
        if len(both_blocks) == 1:
            return [item for block in both_blocks for item in block]
        column1 = both_blocks[0]
        column2 = both_blocks[1]
        sample_blocks = []
        max_length = max(len(column1), len(column2))
        for i in range(max_length):
            block = []
            for x in range(len(column1[i])):
                block.append(column1[i][x])
                block.append(column2[i][x])
            sample_blocks.append(block)
        return sample_blocks

    # def zipper(self, both_blocks):
    #     if len(both_blocks) == 1:
    #         return [w for b in both_blocks for w in b]
    #     col1, col2 = both_blocks
    #     return [[a, b] for i in range(len(col1)) for a, b in zip(col1[i], col2[i])]

    def non_sample_lists(self, conditions, non_sample_other, blocks_to_make): # noqa: C901, PLR0912
        qc_num, wet_qc_num, blank_num, trueblank_num = [], [], [], []
        # find number associated with each nonsample well type
        list_of_keys = list(conditions.keys())
        for key in list_of_keys:
            if conditions[key][0] == "QC":
                qc_num.append(int(key))
            if conditions[key][0] == "WetQC":
                wet_qc_num.append(int(key))
            if conditions[key][0] == "Blank":
                blank_num.append(int(key))
            if conditions[key][0] == "TrueBlank":
                trueblank_num.append(int(key))
        # remove non sample wells into new list
        qc_list, wet_qc_list, blank_list, trueblank_list = [], [], [], []
        for i, block in enumerate(
            non_sample_other[:],
        ):  # don't change this! [:] iterates over copy of original list and edits original
            for well in block[:]:  # same here
                if qc_num:
                    for num in qc_num:
                        if well[0] == num:
                            qc_list.append(well)
                            non_sample_other[i].remove(well)
                if wet_qc_num:
                    for num in wet_qc_num:
                        if well[0] == num:
                            wet_qc_list.append(well)
                            non_sample_other[i].remove(well)
                if blank_num:
                    for num in blank_num:
                        if well[0] == num:
                            blank_list.append(well)
                            non_sample_other[i].remove(well)
                if trueblank_num:
                    for num in trueblank_num:
                        if well[0] == num:
                            trueblank_list.append(well)
                            non_sample_other[i].remove(well)

        nonsample_objects = [
            [qc_list, qc_num],
            [wet_qc_list, wet_qc_num],
            [blank_list, blank_num],
            [trueblank_list, trueblank_num],
        ]
        # raise ValueError(f'Check nonsample_obects: {nonsample_objects}')
        # check number of items to add
        list_nonsample_blocks, adding_check = [], []
        for _ in range(blocks_to_make):
            nonsample_block = []
            for pair in nonsample_objects:
                if pair[0]:
                    for num in pair[1]:
                        num_list = [well for well in pair[0] if well[0] == num]
                        nonsample_block.extend(
                            num_list[0 : self.safe_int(conditions[num][12], default=0)],
                        )
                        adding_check.append(
                            self.safe_int(conditions[num][12], default=0),
                        )
                        for well in num_list[
                            : self.safe_int(conditions[num][12], default=0)
                        ]:
                            pair[0].remove(well)
            list_nonsample_blocks.append(nonsample_block)
        return list_nonsample_blocks

    def combine_samples_and_nonsamples(
        self,
        nonsample_before,
        nonsample_after,
        sample_blocks,
        non_sample_blocks,
        qc_frequency,
        conditions,
    ):
        # Add block numbers
        sample_blocks = self.tag_blocks(sample_blocks)
        samples_flat = [w for b in sample_blocks for w in b]
        blocks_to_make = len(samples_flat) // qc_frequency
        blocks_to_make = 0 if np.isnan(blocks_to_make) else blocks_to_make
        list_nonsample_blocks = self.non_sample_lists(
            conditions,
            non_sample_blocks,
            blocks_to_make,
        )

        samples_and_non, temp, counter = [], [], 0
        if nonsample_before:
            nonsample_before = self.tag_blocks(nonsample_before, tag="pre")
            samples_and_non.append([w for b in nonsample_before for w in b])

        for w in samples_flat:
            temp.append(w)
            counter += 1
            if counter == qc_frequency:
                samples_and_non += [temp, list_nonsample_blocks.pop(0)]
                temp, counter = [], 0
        if temp:
            samples_and_non.append(temp)

        if nonsample_after:
            nonsample_after = self.tag_blocks(nonsample_after, tag="post")
            samples_and_non.append([w for b in nonsample_after for w in b])

        samples_and_non = self.tag_blocks(samples_and_non, tag="other")

        return [b for b in samples_and_non if b != []]


    def tag_blocks(self, non_flat_list, tag=None):
        for i, block in enumerate(non_flat_list, 1):
            for w in block:
                if len(w) < 3:
                    if tag:
                        w.append(f"{tag}")
                    else:
                        w.append(f"blo{i}")
        return non_flat_list

    def two_xp_zipper(
        self,
        flat_list_1,
        flat_list_2,
        two_xp_tb,
        conditions,
        two_xp_tb_location,
    ):
        if not two_xp_tb or two_xp_tb == "None":
            msg = "Error: When more than one experiment is run on one worklist, a trueblank well must be specified in cell AM37 of the excel sheet."
            raise ValueError(
                msg,
            )
        tb_well = [two_xp_tb, two_xp_tb_location[0][1], "end"]

        flat_list_1, flat_list_2 = (
            self.flattener(self.tag_blocks(flat_list_1)),
            self.flattener(self.tag_blocks(flat_list_2)),
        )

        # equalize lengths
        diff = len(flat_list_1) - len(flat_list_2)
        if diff > 0:
            flat_list_2 += [tb_well] * diff
        elif diff < 0:
            flat_list_1 += [tb_well] * (-diff)

        # interleave
        return [v for pair in zip(flat_list_1, flat_list_2, strict=False) for v in pair]

    def flattener(self, final_list):
        """Flatten nested blocks into a list of [x,y,z] rows."""
        # unwrap extra outer wrappers like [[[...]]]
        while (
            isinstance(final_list, list)
            and len(final_list) == 1
            and isinstance(final_list[0], list)
        ):
            final_list = final_list[0]

        out = []
        for block in final_list:
            if not block:
                continue
            for row in block:
                if row:
                    out.append(row)

        return out

    def rep_tracker(self, flattened, conditions):
        reps = []
        rep_counters = {}
        for well in flattened:
            if isinstance(well, list) and len(well) > 2:
                try:
                    condition = int(well[0])
                    if condition in conditions:
                        if condition not in rep_counters:
                            rep_counters[condition] = 1

                        elif condition in rep_counters:
                            rep_counters[condition] += 1
                        reps.append(rep_counters[condition])
                    else:
                        msg = f"Condition {condition} not found in conditions dictionary."
                        raise KeyError(
                            msg,
                        )
                except ValueError:
                    condition = well[0]
                    if condition in conditions:
                        if condition not in rep_counters:
                            rep_counters[condition] = 1

                        elif condition in rep_counters:
                            rep_counters[condition] += 1
                        reps.append(rep_counters[condition])
                    # raise ValueError(f"Invalid condition value '{well[0]}' in well {well}.")
            else:
                reps.append(
                    None,
                )  # If well is not a valid list or doesn't have enough elements
        return reps

    def attach_lib_two_xp(
        self,
        two_xp_flat_list,
        separate_lib1,
        separate_lib2,
        two_xp_tb,
        two_xp_tb_location,
        lib_placement,
        lib_same,
    ):
        """Attach library experiments for two-experiment runs.
        Inserts TB wells every other position during library runs.
        """
        # Flatten nested lists
        separate_lib1 = (
            [item for sublist in separate_lib1 for item in sublist]
            if separate_lib1
            else []
        )
        separate_lib2 = (
            [item for sublist in separate_lib2 for item in sublist]
            if separate_lib2
            else []
        )

        # Tag wells with their library identity
        if separate_lib1:
            for well in separate_lib1:
                well.append("lib1")
        if separate_lib2:
            for well in separate_lib2:
                well.append("lib2")

        tag = "pre" if lib_placement.upper() == "AFTER" else "post"

        tb_well = [two_xp_tb, two_xp_tb_location[0][1], tag]
        to_add = []

        def interweave_with_tb(lib):
            """Insert TB wells every other element of a library list."""
            seq = []
            for well in lib:
                seq.append(well)
                seq.append(tb_well)  # always follow with TB
            return seq

        if lib_same.upper() == "NO":
            # Run libraries separately, TB every other
            if separate_lib1:
                to_add.extend(interweave_with_tb(separate_lib1))
            if separate_lib2:
                to_add.extend(interweave_with_tb(separate_lib2))

        elif lib_same.upper() == "YES":
            if separate_lib1 and separate_lib2:
                # Balance lengths
                if len(separate_lib1) > len(separate_lib2):
                    separate_lib2.extend(
                        [tb_well] * (len(separate_lib1) - len(separate_lib2)),
                    )
                elif len(separate_lib2) > len(separate_lib1):
                    separate_lib1.extend(
                        [tb_well] * (len(separate_lib2) - len(separate_lib1)),
                    )
                # Interleave across libraries with TBs
                for i in range(len(separate_lib1)):
                    to_add.append(separate_lib1[i])
                    to_add.append(tb_well)
                    to_add.append(separate_lib2[i])
                    to_add.append(tb_well)
            elif separate_lib1:
                to_add.extend(interweave_with_tb(separate_lib1))
            elif separate_lib2:
                to_add.extend(interweave_with_tb(separate_lib2))

        else:  # Fallback
            if separate_lib1:
                to_add.extend(interweave_with_tb(separate_lib1))
            if separate_lib2:
                to_add.extend(interweave_with_tb(separate_lib2))
            # safety flush
            to_add.extend([tb_well, tb_well])
        # Place libraries before or after main experiment
        to_add.extend(
            [tb_well, tb_well] * 5,
        )  # buffer TBs between library and main experiment

        if lib_placement.upper() == "BEFORE":
            return to_add + two_xp_flat_list
        # default After
        return two_xp_flat_list + to_add

    def split_sysvalid_by_type(self, sysvalid_list):
        groups = defaultdict(list)
        for well in sysvalid_list:
            groups[well[0]].append(well)
        return list(groups.values())

    def pop_all_columns_per_group(self, sysvalid_groups, new_flat_list, missing_sv):
        """For each group, insert lc_number copies before moving to the next group."""
        for group in sysvalid_groups:
            if group:
                well = group.pop(0)
                new_flat_list.extend([well] * self.lc_number)
            else:
                missing_sv += self.lc_number
        return missing_sv

    def insert_sys_qc(
        self,
        flattened_list,
        sysvalid_list,
        sysvalid_interval,
        two_xp_tb,
        two_xp_tb_location,
        full_conditions,
    ):
        lc_number = self.lc_number
        missing_sv = 0
        sysval_copy = sysvalid_list.copy()

        if len(sysvalid_list) == 0:
            return flattened_list

        sysvalid_interval = int(sysvalid_interval)
        # raise ValueError(f"Check SYSVAL format:\n {two_xp_tb}\n {two_xp_tb_location}\n {full_conditions}")
        tb_well = [two_xp_tb, two_xp_tb_location[0][1], "other"]

        # Tag all wells with 'SysQC'
        for well in sysvalid_list:
            well.append("SysQC")

        # Split into per-type groups (one group per unique first element)
        sysvalid_groups = self.split_sysvalid_by_type(sysvalid_list)

        new_flat_list = []

        # Prepend one well from each group at the start
        missing_sv = self.pop_all_columns_per_group(
            sysvalid_groups,
            new_flat_list,
            missing_sv,
        )

        # Walk through flattened_list in chunks, inserting SysQC between each
        for i in range(0, len(flattened_list), sysvalid_interval):
            new_flat_list.extend(flattened_list[i : i + sysvalid_interval])

            if i + sysvalid_interval < len(flattened_list):
                if any(
                    "LIB" in new_flat_list[-j][2].upper()
                    or "LIB" in full_conditions[new_flat_list[-j][0]][0].upper()
                    for j in range(1, lc_number + 1)
                ):
                    new_flat_list.extend([tb_well] * lc_number)
                # Insert all columns for each group in order
                missing_sv = self.pop_all_columns_per_group(
                    sysvalid_groups,
                    new_flat_list,
                    missing_sv,
                )

        # Append one well from each group at the end
        missing_sv = self.pop_all_columns_per_group(
            sysvalid_groups,
            new_flat_list,
            missing_sv,
        )

        if missing_sv > 0 and sysval_copy:
            pass

        return new_flat_list

    def append_tb_condition(
        self,
        all_c,
        c1,
        c2,
        found_tb,
        sysvalid_condition=None,
        sysvalid_num=None,
    ):
        c1 = {int(k): v for k, v in c1.items()}
        c2 = {int(k): v for k, v in c2.items()}
        merged = {**c1, **c2}
        for _, row in sorted(merged.items()):
            if row and row[0] == "TrueBlank":
                all_c[100] = row
        return all_c

    def default_tb_metadata(
        self,
        conditions,
        sysvalid_condition=None,
        sysvalid_num=None,
    ):
        default_metadata = conditions[100]
        if sysvalid_condition and sysvalid_num in sysvalid_condition:
            sysval_metadata = sysvalid_condition[sysvalid_num]
            default_metadata[2:10] = sysval_metadata[
                2:10
            ]  # borrow metadata from System Validation if available
        conditions[100] = (
            default_metadata  # assign default metadata to the trueblank condition
        )
        return conditions

    def extract_file_info(
        self,
        flattened,
        sysvalid_list,
        sysvalid_interval,
        two_xp_tb,
        two_xp_tb_location,
        conditions,
    ):
        flattened = self.insert_sys_qc(
            flattened,
            sysvalid_list,
            sysvalid_interval,
            two_xp_tb,
            two_xp_tb_location,
            conditions,
        )
        well_conditions, block_runs, positions, inj_vols, reps, msmethods, lcmethods = (
            [],
            [],
            [],
            [],
            [],
            [],
            [],
        )
        well_conditions.extend([int(w[0]) for w in flattened])
        block_runs.extend([w[2] for w in flattened])
        positions.extend([w[1] for w in flattened])
        inj_vols.extend([self.inj_vol[int(w[0])] for w in flattened])
        reps = self.rep_tracker(flattened, conditions)
        msmethods.extend([conditions[int(w[0])][4] for w in flattened])
        lcmethods.extend([conditions[int(w[0])][8] for w in flattened])
        return (
            well_conditions,
            block_runs,
            positions,
            inj_vols,
            reps,
            msmethods,
            lcmethods,
        )

    def block(self): # noqa: C901, PLR0912, PLR0915
        all_wells_flat, two_xp_tb_location = [], []

        if self.cond_range1.upper() == "ALL":  # one experiment, 1 or 2 column system
            conditions, two_xp_tb, found_tb = self.check_for_trueblank(
                self.all_conditions,
            )
            sysvalid_condition, sysvalid_num, found_sysvalid = self.check_for_sysvalid(
                self.all_conditions,
            )
            for key in self.plates:
                all_wells_flat.extend(
                    self.process_plate(self.plates[key], key, self.wet_amounts),
                )
                two_xp_tb_location.extend(
                    self.process_plate(
                        self.plates[key],
                        key,
                        self.wet_amounts,
                        f"{two_xp_tb}-{two_xp_tb}",
                    ),
                )
            for key in self.solvent_vials:
                all_wells_flat.extend(
                    self.process_solvent_vials(
                        self.solvent_vials[key],
                        key,
                        self.wet_amounts,
                    ),
                )
            if not found_tb:
                all_wells_flat.append([two_xp_tb, "R5"])
                two_xp_tb_location.append([two_xp_tb, "R5"])
            self.compare_wells_and_counts(all_wells_flat, conditions, self.wet_amounts)
            if self.lc_number == SINGLE_CHANNEL:
                (
                    nonsample_before,
                    nonsample_after,
                    nonsample_other,
                    column1,
                    sysvalid_list,
                    separate_lib1,
                ) = self.column_sorter(
                    all_wells_flat,
                    conditions,
                    self.num_to_run,
                    self.lc_number,
                    self.lib_placement,
                    self.cond_range1,
                    found_tb,
                    two_xp_tb,
                    found_sysvalid,
                    sysvalid_condition,
                )
                both_blocks, num_blocks = self.blocker(conditions, self.even, column1)
            elif self.lc_number == DUAL_CHANNEL:
                (
                    nonsample_before,
                    nonsample_after,
                    nonsample_other,
                    column1,
                    column2,
                    sysvalid_list,
                    separate_lib1,
                ) = self.column_sorter(
                    all_wells_flat,
                    conditions,
                    self.num_to_run,
                    self.lc_number,
                    self.lib_placement,
                    self.cond_range1,
                    found_tb,
                    two_xp_tb,
                    found_sysvalid,
                    sysvalid_condition,
                )
                both_blocks, num_blocks = self.blocker(
                    conditions,
                    self.even,
                    column1,
                    column2,
                )
            nonsample_blocks = self.nonsample_blocker(
                self.lc_number,
                nonsample_other,
                num_blocks,
                conditions,
                len(all_wells_flat),
            )
            sample_blocks = self.zipper(both_blocks)
            non_flat_list = self.combine_samples_and_nonsamples(
                nonsample_before,
                nonsample_after,
                sample_blocks,
                nonsample_blocks,
                self.qc_frequency,
                conditions,
            )
            # zipper to make flat list and add block labels
            flat_list = [w for b in non_flat_list for w in b]

            if not found_tb:
                conditions = self.default_tb_metadata(
                    conditions,
                    sysvalid_condition,
                    sysvalid_num,
                )
            (
                well_conditions,
                block_runs,
                positions,
                inj_vols,
                reps,
                msmethods,
                lcmethods,
            ) = self.extract_file_info(
                flat_list,
                sysvalid_list,
                self.sysvalid_interval,
                two_xp_tb,
                two_xp_tb_location,
                conditions,
            )

        elif (
            self.cond_range1.upper() != "ALL" and self.lc_number == DUAL_CHANNEL
        ):  # two experiments, 2 column system
            lc_number = 1
            conditions1, conditions2, two_xp_tb, found_tb = self.check_for_trueblank(
                self.conditions1,
                self.conditions2,
            )
            sysvalid_condition, sysvalid_num, found_sysvalid = self.check_for_sysvalid(
                self.all_conditions,
            )

            all_wells_flat1, all_wells_flat2, two_xp_tb_location = [], [], []
            for key in self.plates:
                all_wells_flat1.extend(
                    self.process_plate(
                        self.plates[key],
                        key,
                        self.wet_amounts,
                        self.cond_range1,
                    ),
                )
                all_wells_flat2.extend(
                    self.process_plate(
                        self.plates[key],
                        key,
                        self.wet_amounts,
                        self.cond_range2,
                    ),
                )
                all_wells_flat2.extend(
                    self.process_plate(
                        self.plates[key],
                        key,
                        self.wet_amounts,
                        f"{sysvalid_num}-{sysvalid_num}",
                    ),
                )
                if found_tb:
                    two_xp_tb_location.extend(
                        self.process_plate(
                            self.plates[key],
                            key,
                            self.wet_amounts,
                            f"{two_xp_tb}-{two_xp_tb}",
                        ),
                    )
            for key in self.solvent_vials:
                all_wells_flat1.extend(
                    self.process_solvent_vials(
                        self.solvent_vials[key],
                        key,
                        self.wet_amounts,
                        self.cond_range1,
                    ),
                )
                all_wells_flat2.extend(
                    self.process_solvent_vials(
                        self.solvent_vials[key],
                        key,
                        self.wet_amounts,
                        self.cond_range2,
                    ),
                )
            if not found_tb:
                two_xp_tb_location.append([two_xp_tb, "R5"])
                all_wells_flat1.append([two_xp_tb, "R5"])
                all_wells_flat2.append([two_xp_tb, "R5"])

            # sort the wells in groups so they can be processed according to run type
            (
                nonsample_before1,
                nonsample_after1,
                nonsample_other1,
                exp1col1,
                sysvalid_list,
                separate_lib1,
            ) = self.column_sorter(
                all_wells_flat1,
                conditions1,
                self.num_to_run,
                lc_number,
                self.lib_placement,
                self.cond_range1,
                found_tb,
                two_xp_tb,
                found_sysvalid,
                sysvalid_condition,
            )  # cond_range1 IS CORRECT!!! It checks of cond_range1.upper() == "ALL"
            both_blocks1, num_blocks1 = self.blocker(conditions1, self.even, exp1col1)
            (
                nonsample_before2,
                nonsample_after2,
                nonsample_other2,
                exp2col1,
                sysvalid_list,
                separate_lib2,
            ) = self.column_sorter(
                all_wells_flat2,
                conditions2,
                self.num_to_run,
                lc_number,
                self.lib_placement,
                self.cond_range1,
                found_tb,
                two_xp_tb,
                found_sysvalid,
                sysvalid_condition,
            )  # cond_range1 IS CORRECT!!! It checks of cond_range1.upper() == "ALL"
            both_blocks2, num_blocks2 = self.blocker(conditions2, self.even, exp2col1)

            nonsample_blocks1 = self.nonsample_blocker(
                lc_number,
                nonsample_other1,
                num_blocks1,
                conditions1,
                len(all_wells_flat1),
            )
            nonsample_blocks2 = self.nonsample_blocker(
                lc_number,
                nonsample_other2,
                num_blocks2,
                conditions2,
                len(all_wells_flat2),
            )

            sample_blocks1 = [
                item for block in both_blocks1 for item in block
            ]  # remove one layer of list from each list of lists
            sample_blocks2 = [item for block in both_blocks2 for item in block]

            non_flat_list1 = self.combine_samples_and_nonsamples(
                nonsample_before1,
                nonsample_after1,
                sample_blocks1,
                nonsample_blocks1,
                self.qc_frequency,
                conditions1,
            )
            non_flat_list2 = self.combine_samples_and_nonsamples(
                nonsample_before2,
                nonsample_after2,
                sample_blocks2,
                nonsample_blocks2,
                self.qc_frequency,
                conditions2,
            )

            two_xp_flat_list = self.two_xp_zipper(
                non_flat_list1,
                non_flat_list2,
                two_xp_tb,
                self.all_conditions,
                two_xp_tb_location,
            )
            two_xp_flat_list = self.attach_lib_two_xp(
                two_xp_flat_list,
                separate_lib1,
                separate_lib2,
                two_xp_tb,
                two_xp_tb_location,
                self.lib_placement,
                self.lib_same,
            )

            if not found_tb:
                conditions = self.append_tb_condition(
                    self.all_conditions,
                    conditions1,
                    conditions2,
                    found_tb,
                )
                conditions = self.default_tb_metadata(
                    conditions,
                    sysvalid_condition,
                    sysvalid_num,
                )
            (
                well_conditions,
                block_runs,
                positions,
                inj_vols,
                reps,
                msmethods,
                lcmethods,
            ) = self.extract_file_info(
                two_xp_flat_list,
                sysvalid_list,
                self.sysvalid_interval,
                two_xp_tb,
                two_xp_tb_location,
                conditions,
            )

        else:
            msg = (
                "Experiment conditions cannot be run due to missing or invalid configuration.\n"
                "Verify that all required experiment fields are correctly filled in the Excel sheet.\n"
                "If there is only one experiment the library values should be the same. If there are two experiments you must use a 2 column system."
            )
            raise ValueError(
                msg,
            )
        return [
            well_conditions,
            block_runs,
            positions,
            inj_vols,
            reps,
            msmethods,
            lcmethods,
            conditions,
        ]
