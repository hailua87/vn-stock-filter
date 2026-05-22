"""
Top liquid Vietnamese stocks — used as initial universe when no cache exists.

This list contains ~500 most liquid tickers across HOSE/HNX/UPCOM, ranked by
historical average turnover (GTGD). Used by data_fetcher to prioritize which
stocks to fetch when rate-limited.

Updated: 2026 — based on VN30, VN100, HNX30 index components and known high-volume names.

Usage:
    from scanner.top_liquid import TOP_LIQUID
    # Returns list of (ticker, exchange) tuples
"""

# Tier 1: VN30 + known mega-caps (highest priority)
HOSE_TIER1 = [
    'VCB', 'BID', 'CTG', 'TCB', 'MBB', 'VPB', 'STB', 'HDB', 'ACB', 'SHB',
    'VHM', 'VIC', 'VRE', 'NVL', 'KDH', 'PDR', 'DXG', 'HDG', 'NLG', 'BCM',
    'HPG', 'HSG', 'NKG', 'GVR', 'DGC', 'DCM', 'DPM',
    'FPT', 'MWG', 'PNJ', 'MSN', 'VNM', 'SAB', 'VEA',
    'GAS', 'PLX', 'POW', 'PVD', 'PVS',
    'SSI', 'VND', 'HCM', 'VCI', 'MBS',
    'REE', 'GMD', 'PHR', 'VIB', 'EIB',
    'BVH', 'BCG', 'GEX', 'KBC', 'IDC', 'BMP',
]

# Tier 2: HOSE liquid mid-caps
HOSE_TIER2 = [
    'AAA', 'AGG', 'ANV', 'ASM', 'BAF', 'BCE', 'BFC', 'BMC', 'BSI', 'BWE',
    'CCL', 'CII', 'CKG', 'CMG', 'CMX', 'CNG', 'CRE', 'CSV', 'CTD', 'CTF',
    'CTI', 'CTR', 'CTS', 'D2D', 'DBC', 'DBD', 'DCL', 'DGW', 'DHC', 'DHG',
    'DIG', 'DLG', 'DPG', 'DRC', 'DRH', 'DSN', 'DXS', 'EVE', 'EVG', 'FCN',
    'FIR', 'FIT', 'FMC', 'FRT', 'FTS', 'GAB', 'GDT', 'GIL', 'GMC', 'GMH',
    'HAG', 'HAH', 'HAR', 'HAS', 'HAX', 'HBC', 'HCD', 'HCM', 'HHS', 'HHV',
    'HID', 'HII', 'HMC', 'HNG', 'HPX', 'HQC', 'HT1', 'HTN', 'HVH', 'HVN',
    'ICT', 'IDI', 'IJC', 'IMP', 'ITA', 'ITC', 'ITD', 'JVC', 'KDC', 'KHG',
    'KHP', 'KMR', 'KOS', 'KPF', 'KSB', 'L10', 'LAF', 'LCG', 'LDG', 'LGC',
    'LGL', 'LHG', 'LIX', 'LM8', 'LPB', 'LSS', 'MCG', 'MDG', 'MHC', 'MIG',
    'MSB', 'NAF', 'NAV', 'NBB', 'NCT', 'NHA', 'NHH', 'NHT', 'NNC', 'NTL',
    'NVT', 'OCB', 'OGC', 'OPC', 'ORS', 'PAC', 'PAN', 'PC1', 'PDN', 'PET',
    'PGC', 'PGD', 'PGV', 'PHC', 'PHR', 'PIT', 'PLP', 'PME', 'PNC', 'POM',
    'PPC', 'PSH', 'PTB', 'PTC', 'PTL', 'PVT', 'QBS', 'QCG', 'RAL', 'RDP',
    'SAM', 'SAV', 'SBT', 'SBV', 'SC5', 'SCR', 'SCS', 'SFG', 'SFI', 'SGT',
    'SHA', 'SHI', 'SHP', 'SII', 'SJD', 'SJF', 'SJS', 'SKG', 'SMA', 'SMC',
    'SPM', 'SRC', 'SRF', 'ST8', 'SVC', 'SVI', 'SVT', 'SZC', 'SZL', 'TBC',
    'TCD', 'TCH', 'TCL', 'TCM', 'TCO', 'TCR', 'TDC', 'TDG', 'TDH', 'TDM',
    'TDP', 'TIP', 'TIX', 'TLD', 'TLG', 'TLH', 'TMS', 'TMT', 'TNA', 'TNC',
    'TNH', 'TNI', 'TNT', 'TPB', 'TRA', 'TRC', 'TSC', 'TTA', 'TTB', 'TTF',
    'TV2', 'TVB', 'TVS', 'TVT', 'TYA', 'UDC', 'UIC', 'VAF', 'VCA', 'VCF',
    'VFG', 'VGC', 'VHC', 'VIP', 'VIX', 'VMD', 'VNE', 'VNG', 'VNL', 'VNS',
    'VOS', 'VPG', 'VPH', 'VPI', 'VPS', 'VSC', 'VSH', 'VSI', 'VTB', 'VTO',
    'YBM', 'YEG',
]

# HNX liquid
HNX_TIER1 = [
    'SHS', 'CEO', 'IDC', 'PVS', 'TNG', 'MBS', 'VCS', 'PVI', 'HUT', 'BVS',
    'NTP', 'LAS', 'TVC', 'VC3', 'TIG', 'VIG', 'AAV', 'API', 'APS', 'ART',
    'BCC', 'BII', 'BVB', 'CAN', 'CAP', 'CIA', 'CLM', 'CMS', 'CSC', 'CTC',
    'CTP', 'DDG', 'DHT', 'DL1', 'DNC', 'DNP', 'DST', 'DTD', 'DTK', 'DXP',
    'EBS', 'EID', 'GKM', 'HHC', 'HJS', 'HLD', 'HMR', 'HOM', 'HTP', 'IDJ',
    'IDV', 'INN', 'IPA', 'KKC', 'KSF', 'KTT', 'L14', 'L18', 'LIG', 'MBG',
    'MCO', 'MED', 'MST', 'NAG', 'NBC', 'NDN', 'NRC', 'NSH', 'OCH', 'ONE',
    'PGS', 'PHN', 'PIA', 'PIC', 'PLC', 'PMC', 'POT', 'PPE', 'PPS', 'PSD',
    'PSI', 'PSW', 'PTI', 'PVC', 'PVG', 'PVL', 'QST', 'S99', 'SCG', 'SCI',
    'SD5', 'SD6', 'SDA', 'SDC', 'SDG', 'SDT', 'SED', 'SFN', 'SGH', 'SHE',
    'SHN', 'SLS', 'SMN', 'SPI', 'SRA', 'SVN', 'TAR', 'TC6', 'TFC', 'TFI',
    'THD', 'THS', 'TKC', 'TKU', 'TMC', 'TNG', 'TPH', 'TTL', 'TTT', 'TVD',
    'UNI', 'VBC', 'VC2', 'VC7', 'VC9', 'VCG', 'VDL', 'VE3', 'VHL', 'VIE',
    'VMC', 'VMS', 'VTC', 'VTV', 'VTZ', 'WSS', 'XMC',
]

# UPCOM liquid
UPCOM_TIER1 = [
    'ACV', 'BSR', 'VEA', 'VGI', 'OIL', 'QNS', 'VTP', 'MCH', 'MSR', 'SIP',
    'VGT', 'LTG', 'FOX', 'MFS', 'BVB', 'AAS', 'ABB', 'ABI', 'ABR', 'ABS',
    'ACE', 'ACS', 'ADP', 'ADS', 'AGF', 'AGM', 'AGP', 'AGX', 'ALV', 'AMD',
    'AME', 'APF', 'APH', 'APP', 'ART', 'ASG', 'ASP', 'AST', 'ATB', 'ATG',
    'ATS', 'AVF', 'AVG', 'BCA', 'BCB', 'BCV', 'BDG', 'BDT', 'BDW', 'BED',
    'BHA', 'BHN', 'BHV', 'BIG', 'BLT', 'BMD', 'BMG', 'BMN', 'BNW', 'BOT',
    'BSA', 'BSG', 'BSI', 'BSP', 'BSQ', 'BST', 'BT1', 'BT6', 'BTB', 'BTD',
    'BTN', 'BTW', 'BTV', 'BWA', 'BWS', 'C12', 'C32', 'C47', 'C71', 'C92',
    'CAB', 'CAD', 'CAG', 'CBI', 'CBS', 'CC1', 'CC4', 'CCM', 'CCP', 'CCR',
    'CCT', 'CCV', 'CDH', 'CDO', 'CDR', 'CE1', 'CEG', 'CFM', 'CFV', 'CH5',
    'CHS', 'CI5', 'CID', 'CIG', 'CKA', 'CKD', 'CKV', 'CLG', 'CLH', 'CLL',
    'CLM', 'CLW', 'CMC', 'CMD', 'CMF', 'CMI', 'CMK', 'CMN', 'CMP', 'CMT',
    'CMV', 'CNA', 'CNC', 'CNN', 'COM', 'CPA', 'CPC', 'CPH', 'CQN', 'CST',
    'CT3', 'CT6', 'CTA', 'CTB', 'CTW', 'CVN', 'CVT', 'CX8', 'D11', 'D17',
    'DAC', 'DAD', 'DAE', 'DAH', 'DAN', 'DAP', 'DAR', 'DAS', 'DBM', 'DBT',
    'DC1', 'DC2', 'DC4', 'DCF', 'DCH', 'DCR', 'DCS', 'DDH', 'DDM', 'DDV',
    'DFC', 'DFF', 'DGT', 'DHA', 'DHB', 'DHD', 'DHM', 'DHN', 'DHP', 'DKC',
    'DLD', 'DM7', 'DMC', 'DMN', 'DMS', 'DNA', 'DND', 'DNE', 'DNH', 'DNL',
    'DNM', 'DNN', 'DNT', 'DNW', 'DNY', 'DOC', 'DP1', 'DP2', 'DP3', 'DPP',
    'DPS', 'DQC', 'DRG', 'DRI', 'DRL', 'DSG', 'DSP', 'DTA', 'DTB', 'DTC',
    'DTE', 'DTG', 'DTI', 'DTL', 'DTP', 'DTT', 'DTV', 'DVC', 'DVG', 'DVN',
]


def get_top_liquid_tickers() -> list:
    """
    Return ~500 most liquid VN tickers as list of (ticker, exchange) tuples.
    Used as initial universe before cache is built.
    """
    result = []
    seen = set()

    for tk in HOSE_TIER1 + HOSE_TIER2:
        if tk not in seen:
            result.append((tk, 'HOSE'))
            seen.add(tk)

    for tk in HNX_TIER1:
        if tk not in seen:
            result.append((tk, 'HNX'))
            seen.add(tk)

    for tk in UPCOM_TIER1:
        if tk not in seen:
            result.append((tk, 'UPCOM'))
            seen.add(tk)

    return result
