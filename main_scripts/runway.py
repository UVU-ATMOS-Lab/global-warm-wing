import json5
import math
from typing import Any

# pathing
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.dependencies import *


RELATIVE_PATH = "warm_wing/input/"
def loadJson5(path: str) -> dict[str, Any]:
    """path is relative to warm_wing/input/"""
    with open(RELATIVE_PATH + path, "r") as f:
        return json5.load(f)
        
        
def runwayLength(
    elevationMeters: int|float = 0, 
    tempCelsius: float = 0,
    airframe: dict = 0,
) -> float:
    """
    Return runway length required for a set of elevation, temperature for a given model of aircraft
    otherwise:
    -1 for airframe not in list
    math.inf if runway will never be long enough to accommodate
    """
    if not isInAirframes(airframe['model']):
        return -1
    
    dn = dryAirDensity(elevationMeters, tempCelsius)
    print(f"        {dn:.3f} kg/m^3 air density with temp {tempCelsius} C && elevation {elevationMeters} m")

    # formula: runwayLength = -(h / airDensity) * ln(1 - (g / airDensity))
    
    # check validity ln(must > 0), so ln(1-x must < 1), so g must < airDensity
    # otherwise ln might have invalid input (invalid here means infinite runway)
    logValidity = airframe["g"] < dn
    if not logValidity: # lg error, cannot takeoff
        return math.inf
    
    # python math.log same as ln()
    # this formula is listed in airframes.json5
    return 1000 * (0 - (airframe["h"] / dn) * math.log(1 - (airframe["g"] / dn)))
    
    
def listAllAirframes() -> None:
    """
    List all aircraft models which have coefficients in airframes.json5
    e.g. they have an air density-runway length function
    """
    af = loadJson5("airframes.json5")["models"]
    print(f"List of avl. airframes: {[k["model"] for k in af]}\n")


def isInAirframes(airframe: str) -> bool:
    af = loadJson5("airframes.json5")["models"]
    af = [k["model"] for k in af]
    return airframe in af


def runwayTest():
    assert isInAirframes("a330-200")
    assert not isInAirframes("a170") # not a model
    assert runwayLength(0, 0, {"model":"a170"}) == -1
    

if __name__ == "__main__":
    runwayTest()
    
    listAllAirframes()
    airports = loadJson5("airports.json5")["airports"]
    airframes = loadJson5("airframes.json5")["models"]
    
    tempC = -5 # placeholder for temp range future given by IPCC
    
    for ap in airports:
        # inside one airport
        print(f"~~ airport {ap['alias']} [{ap['icao']}] ~~")
        
        for af in airframes:
            # inside a single airframe per airport
            print(f"    {af['mfg']} {af['model']}:")
    
            # for now just the best case scenario (longest runway) ap["rwys"][0]["len"]
            
            #
            rwl = runwayLength(ap["elev"], tempC, af)
            print(f"        {rwl:.1f} m runway needed")
            
            longestRwy = ap["rwys"][0]["len"]
            print(f"        {longestRwy:.1f} m longest runway here")
            canTakeoffLongest = rwl <= longestRwy
            print(f"        {canTakeoffLongest} full weight takeoff")
    
        print("\n-----------------------------------\n")