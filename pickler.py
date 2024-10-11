import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests
import redis
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

CACHE_EXPIRY = 3600  # Cache expires after 1 hour (in seconds)

# Initialize Redis connection
redis_client = redis.Redis(
    host="redis-18572.c240.us-east-1-3.ec2.redns.redis-cloud.com",
    port=18572,
    password="BzrSrz0O42MRRYIyH08Q6xEgZ7wVV0Gk"
)

# ticker list dictionary
ticker_list = {
    "10x Genomics Inc. (TXG)": ["TXG", "10x"],
    "1Life Healthcare Inc. (ONEM)": ["ONEM", "1Life"],
    "2U Inc. (TWOU)": ["TWOU", "2U"],
    "3D Systems Corporation (DDD)": ["DDD", "3D"],
    "3M Company (MMM)": ["MMM", "3M"],
    "8x8 Inc (EGHT)": ["EGHT", "8x8"],
    "A.O. Smith Corporation (AOS)": ["AOS", "A.O."],
    "AAON Inc. (AAON)": ["AAON", "AAON"],
    "Abbott Laboratories (ABT)": ["ABT", "Abbott"],
    "AbbVie Inc. (ABBV)": ["ABBV", "AbbVie"],
    "AbCellera Biologics Inc. (ABCL)": ["ABCL", "AbCellera"],
    "Abercrombie & Fitch Company (ANF)": ["ANF", "Abercrombie"],
    "ABIOMED Inc. (ABMD)": ["ABMD", "ABIOMED"],
    "ABM Industries Incorporated (ABM)": ["ABM", "ABM"],
    "Academy Sports and Outdoors Inc. (ASO)": ["ASO", "Academy"],
    "Acadia Healthcare Company Inc. (ACHC)": ["ACHC", "Acadia"],
    "ACADIA Pharmaceuticals Inc. (ACAD)": ["ACAD", "ACADIA"],
    "Acceleron Pharma Inc. (XLRN)": ["XLRN", "Acceleron"],
    "Accolade Inc. (ACCD)": ["ACCD", "Accolade"],
    "ACI Worldwide Inc. (ACIW)": ["ACIW", "ACI"],
    "Activision Blizzard Inc. (ATVI)": ["ATVI", "Activision"],
    "Acuity Brands Inc. (AYI)": ["AYI", "Acuity"],
    "Acushnet Holdings Corp. (GOLF)": ["GOLF", "Acushnet"],
    "ACV Auctions Inc. (ACVA)": ["ACVA", "ACV"],
    "Adams Diversified Equity Fund Inc. (ADX)": ["ADX", "Adams"],
    "AdaptHealth Corp. (AHCO)": ["AHCO", "AdaptHealth"],
    "Adaptive Biotechnologies Corporation (ADPT)": ["ADPT", "Adaptive"],
    "Adobe Inc. (ADBE)": ["ADBE", "Adobe"],
    "ADT Inc. (ADT)": ["ADT", "ADT"],
    "Adtalem Global Education Inc. (ATGE)": ["ATGE", "Adtalem"],
    "Advance Auto Parts Inc Advance Auto Parts Inc W/I (AAP)": ["AAP", "Advance"],
    "Advanced Drainage Systems Inc. (WMS)": ["WMS", "Advanced"],
    "Advanced Energy Industries Inc. (AEIS)": ["AEIS", "Advanced"],
    "Advanced Micro Devices Inc. (AMD)": ["AMD", "Advanced"],
    "Advantage Solutions Inc. (ADV)": ["ADV", "Advantage"],
    "AECOM (ACM)": ["ACM", "AECOM"],
    "Aerojet Rocketdyne Holdings Inc. (AJRD)": ["AJRD", "Aerojet"],
    "AeroVironment Inc. (AVAV)": ["AVAV", "AeroVironment"],
    "Affiliated Managers Group Inc. (AMG)": ["AMG", "Affiliated"],
    "Affirm Holdings Inc. (AFRM)": ["AFRM", "Affirm"],
    "AFLAC Incorporated (AFL)": ["AFL", "AFLAC"],
    "AGCO Corporation (AGCO)": ["AGCO", "AGCO"],
    "Agilent Technologies Inc. (A)": ["A", "Agilent"],
    "Agios Pharmaceuticals Inc. (AGIO)": ["AGIO", "Agios"],
    "AGNC Investment Corp. (AGNC)": ["AGNC", "AGNC"],
    "Agnico Eagle Mines Limited (AEM)": ["AEM", "Agnico"],
    "Agree Realty Corporation (ADC)": ["ADC", "Agree"],
    "Air Lease Corporation (AL)": ["AL", "Air"],
    "Air Products and Chemicals Inc. (APD)": ["APD", "Air"],
    "Airbnb Inc. (ABNB)": ["ABNB", "Airbnb"],
    "Akamai Technologies Inc. (AKAM)": ["AKAM", "Akamai"],
    "Alamos Gold Inc. (AGI)": ["AGI", "Alamos"],
    "Alarm.com Holdings Inc. (ALRM)": ["ALRM", "Alarm.com"],
    "Alaska Air Group Inc. (ALK)": ["ALK", "Alaska"],
    "Albany International Corporation (AIN)": ["AIN", "Albany"],
    "Albemarle Corporation (ALB)": ["ALB", "Albemarle"],
    "Albertsons Companies Inc. (ACI)": ["ACI", "Albertsons"],
    "Alexandria Real Estate Equities Inc. (ARE)": ["ARE", "Alexandria"],
    "Alexion Pharmaceuticals Inc. (ALXN)": ["ALXN", "Alexion"],
    "Align Technology Inc. (ALGN)": ["ALGN", "Align"],
    "Alignment Healthcare Inc. (ALHC)": ["ALHC", "Alignment"],
    "Allakos Inc. (ALLK)": ["ALLK", "Allakos"],
    "Alleghany Corporation (Y)": ["Y", "Alleghany"],
    "Allegheny Technologies Incorporated (ATI)": ["ATI", "Allegheny"],
    "Allegiant Travel Company (ALGT)": ["ALGT", "Allegiant"],
    "Allegion plc (ALLE)": ["ALLE", "Allegion"],
    "Allegro MicroSystems Inc. (ALGM)": ["ALGM", "Allegro"],
    "Allete Inc. (ALE)": ["ALE", "Allete"],
    "Alliance Data Systems Corporation (ADS)": ["ADS", "Alliance"],
    "AllianceBernstein Holding L.P. Units (AB)": ["AB", "AllianceBernstein"],
    "Alliant Energy Corporation (LNT)": ["LNT", "Alliant"],
    "Allison Transmission Holdings Inc. (ALSN)": ["ALSN", "Allison"],
    "Under Armour Inc. (UA)": ["UA", "Under"],
    "Under Armour Inc. (UAA)": ["UAA", "Under"],
    "Unifirst Corporation (UNF)": ["UNF", "Unifirst"],
    "Union Pacific Corporation (UNP)": ["UNP", "Union"],
    "United Airlines Holdings Inc. (UAL)": ["UAL", "United"],
    "United Bankshares Inc. (UBSI)": ["UBSI", "United"],
    "United Community Banks Inc. (UCBI)": ["UCBI", "United"],
    "United Parcel Service Inc. (UPS)": ["UPS", "United"],
    "United Rentals Inc. (URI)": ["URI", "United"],
    "United States Cellular Corporation (USM)": ["USM", "United"],
    "United States Steel Corporation (X)": ["X", "United"],
    "United Therapeutics Corporation (UTHR)": ["UTHR", "United"],
    "UnitedHealth Group Incorporated (UNH)": ["UNH", "UnitedHealth"],
    "Uniti Group Inc. (UNIT)": ["UNIT", "Uniti"],
    "Unity Software Inc. (U)": ["U", "Unity"],
    "Univar Solutions Inc. (UNVR)": ["UNVR", "Univar"],
    "Universal Display Corporation (OLED)": ["OLED", "Universal"],
    "Universal Health Services Inc. (UHS)": ["UHS", "Universal"],
    "Unum Group (UNM)": ["UNM", "Unum"],
    "Upstart Holdings Inc. (UPST)": ["UPST", "Upstart"],
    "Upwork Inc. (UPWK)": ["UPWK", "Upwork"],
    "Urban Outfitters Inc. (URBN)": ["URBN", "Urban"],
    "US Foods Holding Corp. (USFD)": ["USFD", "US"],
    "USANA Health Sciences Inc. (USNA)": ["USNA", "USANA"],
    "Utz Brands Inc (UTZ)": ["UTZ", "Utz"],
    "UWM Holdings Corporation (UWMC)": ["UWMC", "UWM"],
    "V.F. Corporation (VFC)": ["VFC", "V.F."],
    "Vail Resorts Inc. (MTN)": ["MTN", "Vail"],
    "Valero Energy Corporation (VLO)": ["VLO", "Valero"],
    "Valley National Bancorp (VLY)": ["VLY", "Valley"],
    "Valmont Industries Inc. (VMI)": ["VMI", "Valmont"],
    "Valvoline Inc. (VVV)": ["VVV", "Valvoline"],
    "Varian Medical Systems Inc. (VAR)": ["VAR", "Varian"],
    "Varonis Systems Inc. (VRNS)": ["VRNS", "Varonis"],
    "Vector Group Ltd. (VGR)": ["VGR", "Vector"],
    "Velodyne Lidar Inc. (VLDR)": ["VLDR", "Velodyne"],
    "Ventas Inc. (VTR)": ["VTR", "Ventas"],
    "Veracyte Inc. (VCYT)": ["VCYT", "Veracyte"],
    "VEREIT Inc. (VER)": ["VER", "VEREIT"],
    "Vericel Corporation (VCEL)": ["VCEL", "Vericel"],
    "Verint Systems Inc. (VRNT)": ["VRNT", "Verint"],
    "VeriSign Inc. (VRSN)": ["VRSN", "VeriSign"],
    "Verisk Analytics Inc. (VRSK)": ["VRSK", "Verisk"],
    "Verra Mobility Corporation (VRRM)": ["VRRM", "Verra"],
    "Vertex Inc. (VERX)": ["VERX", "Vertex"],
    "Vertex Pharmaceuticals Incorporated (VRTX)": ["VRTX", "Vertex"],
    "Vertiv Holdings LLC (VRT)": ["VRT", "Vertiv"],
    "ViacomCBS Inc. (VIAC)": ["VIAC", "ViacomCBS"],
    "ViacomCBS Inc. (VIACA)": ["VIACA", "ViacomCBS"],
    "Viant Technology Inc. (DSP)": ["DSP", "Viant"],
    "ViaSat Inc. (VSAT)": ["VSAT", "ViaSat"],
    "Viatris Inc. (VTRS)": ["VTRS", "Viatris"],
    "Viavi Solutions Inc. (VIAV)": ["VIAV", "Viavi"],
    "Vicor Corporation (VICR)": ["VICR", "Vicor"],
    "Viper Energy Partners LP (VNOM)": ["VNOM", "Viper"],
    "Vir Biotechnology Inc. (VIR)": ["VIR", "Vir"],
    "Virtu Financial Inc. (VIRT)": ["VIRT", "Virtu"],
    "Visa Inc. (V)": ["V", "Visa"],
    "Vishay Intertechnology Inc. (VSH)": ["VSH", "Vishay"],
    "Visteon Corporation (VC)": ["VC", "Visteon"],
    "Vmware Inc. (VMW)": ["VMW", "Vmware"],
    "Vonage Holdings Corp. (VG)": ["VG", "Vonage"],
    "Vornado Realty Trust (VNO)": ["VNO", "Vornado"],
    "Voya Financial Inc. (VOYA)": ["VOYA", "Voya"],
    "Vroom Inc. (VRM)": ["VRM", "Vroom"],
    "Vulcan Materials Company (VMC)": ["VMC", "Vulcan"],
    "W. P. Carey Inc. REIT (WPC)": ["WPC", "W."],
    "W.R. Berkley Corporation (WRB)": ["WRB", "W.R."],
    "W.R. Grace & Co. (GRA)": ["GRA", "W.R."],
    "W.W. Grainger Inc. (GWW)": ["GWW", "W.W."],
    "Walgreens Boots Alliance Inc. (WBA)": ["WBA", "Walgreens"],
    "Walker & Dunlop Inc (WD)": ["WD", "Walker"],
    "Walmart Inc. (WMT)": ["WMT", "Walmart"],
    "Walt Disney Company (DIS)": ["DIS", "Disney"],
    "Warner Music Group Corp. (WMG)": ["WMG", "Warner"],
    "Washington Federal Inc. (WAFD)": ["WAFD", "Washington"],
    "Waste Connections Inc. (WCN)": ["WCN", "Waste"],
    "Waste Management Inc. (WM)": ["WM", "Waste"],
    "Waters Corporation (WAT)": ["WAT", "Waters"],
    "Watsco Inc. (WSO)": ["WSO", "Watsco"],
    "Watts Water Technologies Inc. (WTS)": ["WTS", "Watts"],
    "Wayfair Inc. (W)": ["W", "Wayfair"],
    "WD-40 Company (WDFC)": ["WDFC", "WD-40"],
    "Webster Financial Corporation (WBS)": ["WBS", "Webster"],
    "WEC Energy Group Inc. (WEC)": ["WEC", "WEC"],
    "Weingarten Realty Investors (WRI)": ["WRI", "Weingarten"],
    "Wells Fargo & Company (WFC)": ["WFC", "Wells"],
    "Welltower Inc. (WELL)": ["WELL", "Welltower"],
    "Wendy's Company (WEN)": ["WEN", "Wendy's"],
    "Werner Enterprises Inc. (WERN)": ["WERN", "Werner"],
    "WesBanco Inc. (WSBC)": ["WSBC", "WesBanco"],
    "WESCO International Inc. (WCC)": ["WCC", "WESCO"],
    "West Pharmaceutical Services Inc. (WST)": ["WST", "West"],
    "Western Alliance Bancorporation (WAL)": ["WAL", "Western"],
    "Western Digital Corporation (WDC)": ["WDC", "Western"],
    "Western Midstream Partners LP (WES)": ["WES", "Western"],
    "Western Union Company (WU)": ["WU", "Western"],
    "Westinghouse Air Brake Technologies Corporation (WAB)": ["WAB", "Westinghouse"],
    "Westlake Chemical Corporation (WLK)": ["WLK", "Westlake"],
    "WEX Inc. (WEX)": ["WEX", "WEX"],
    "Weyerhaeuser Company (WY)": ["WY", "Weyerhaeuser"],
    "Wheaton Precious Metals Corp (WPM)": ["WPM", "Wheaton"],
    "Whirlpool Corporation (WHR)": ["WHR", "Whirlpool"],
    "White Mountains Insurance Group Ltd. (WTM)": ["WTM", "White"],
    "Williams Companies Inc. (WMB)": ["WMB", "Williams"],
    "Williams-Sonoma Inc. (WSM)": ["WSM", "Williams-Sonoma"],
    "WillScot Mobile Mini Holdings Corp. (WSC)": ["WSC", "WillScot"],
    "Wingstop Inc. (WING)": ["WING", "Wingstop"],
    "Winnebago Industries Inc. (WGO)": ["WGO", "Winnebago"],
    "Wintrust Financial Corporation (WTFC)": ["WTFC", "Wintrust"],
    "Wolverine World Wide Inc. (WWW)": ["WWW", "Wolverine"],
    "Woodward Inc. (WWD)": ["WWD", "Woodward"],
    "Workday Inc. (WDAY)": ["WDAY", "Workday"],
    "Workiva Inc. (WK)": ["WK", "Workiva"],
    "World Fuel Services Corporation (INT)": ["INT", "World"],
    "World Wrestling Entertainment Inc. (WWE)": ["WWE", "World"],
    "Worthington Industries Inc. (WOR)": ["WOR", "Worthington"],
    "WSFS Financial Corporation (WSFS)": ["WSFS", "WSFS"],
    "WW International Inc. (WW)": ["WW", "WW"],
    "Wynn Resorts Limited (WYNN)": ["WYNN", "Wynn"],
    "Xcel Energy Inc. (XEL)": ["XEL", "Xcel"],
    "Xencor Inc. (XNCR)": ["XNCR", "Xencor"],
    "Xenia Hotels & Resorts Inc. (XHR)": ["XHR", "Xenia"],
    "Xerox Holdings Corporation (XRX)": ["XRX", "Xerox"],
    "Xilinx Inc. (XLNX)": ["XLNX", "Xilinx"],
    "Xperi Holding Corporation (XPER)": ["XPER", "Xperi"],
    "XPO Logistics Inc. (XPO)": ["XPO", "XPO"],
    "Xylem Inc. New (XYL)": ["XYL", "Xylem"],
    "Yamana Gold Inc. (AUY)": ["AUY", "Yamana"],
    "Yelp Inc. (YELP)": ["YELP", "Yelp"],
    "YETI Holdings Inc. (YETI)": ["YETI", "YETI"],
    "Yum China Holdings Inc. (YUMC)": ["YUMC", "Yum"],
    "Yum! Brands Inc. (YUM)": ["YUM", "Yum!"],
    "Zebra Technologies Corporation (ZBRA)": ["ZBRA", "Zebra"],
    "Zillow Group Inc. (ZG)": ["ZG", "Zillow"],
    "Zillow Group Inc. Capital Stock (Z)": ["Z", "Zillow"],
    "Zimmer Biomet Holdings Inc. (ZBH)": ["ZBH", "Zimmer"],
    "Zions Bancorporation N.A. (ZION)": ["ZION", "Zions"],
    "Zoetis Inc. (ZTS)": ["ZTS", "Zoetis"],
    "Zoom Video Communications Inc. (ZM)": ["ZM", "Zoom"],
    "ZoomInfo Technologies Inc. (ZI)": ["ZI", "ZoomInfo"],
    "Zscaler Inc. (ZS)": ["ZS", "Zscaler"],
    "Zynga Inc. (ZNGA)": ["ZNGA", "Zynga"],
}
# Reverse lookup dictionary for quick symbol to name mapping
symbol_to_name = {symbol: name for name, (symbol, _) in ticker_list.items()}

def check_cache(ticker):
    cache_key = f"stock_data:{ticker}"
    cached_data = redis_client.get(cache_key)
    if cached_data:
        return json.loads(cached_data)
    return None

def get_stock_data(ticker, force_update=False):
    cache_key = f"stock_data:{ticker}"

    # Check if data is in Redis cache and not forced to update
    if not force_update:
        cached_data = redis_client.get(cache_key)
        if cached_data:
            logging.info(f"Cache hit for {ticker}")
            return json.loads(cached_data)
    logging.info(f"Cache miss for {ticker}, fetching from API")
    # If no cached data or force update, fetch from API
    data = fetch_from_api(ticker)

    # Add company name to the data
    data['company_name'] = symbol_to_name.get(ticker, "Unknown")

    # Cache the new data in Redis
    redis_client.setex(cache_key, CACHE_EXPIRY, json.dumps(data))

    return data

def fetch_from_api(ticker):
    # Get API key from environment vars
    api_key = os.getenv("POLYGON_API_KEY")

    if not api_key:
        raise ValueError("No API key provided")
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?apiKey={api_key}"

    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"API call failed for ticker {ticker}")

def get_company_info(ticker):
    for name, (symbol, short_name) in ticker_list.items():
        if symbol == ticker:
            return {"name": name, "short_name": short_name}
    return None

# Example usage
if __name__ == "__main__":
    # Get stock data for Apple
    apple_data = get_stock_data("AAPL")
    print(f"Apple stock data: {apple_data}")

    # check cache
    print(check_cache("AAPL"))
    print(check_cache("AAPL", force_update=True))

    # Get company info for Apple
    apple_info = get_company_info("AAPL")
    print(f"Apple company info: {apple_info}")
