def dryAirDensityFull(elevation: int|float = 0, temperature: float = 0) -> float:
    """
    return dry air density in kg/m^3
    
    elevation in meters.
    temperature in degrees Celsius.

    The ambient pressure at the given elevation is estimated from the
    barometric formula for the lower troposphere (ISA), then the density
    is obtained from the ideal gas law for dry air.
    """
    # consts
    P0 = 101325.0      # sea-level standard pressure, Pa
    T0 = 288.15        # sea-level standard temperature, K
    L = 0.0065         # temperature lapse rate, K/m
    g = 9.80665        # gravitational acceleration, m/s^2
    M = 0.0289652      # molar mass of dry air, kg/mol
    R = 8.31446        # universal gas constant, J/(mol*K)

    # Pressure at elevation (barometric formula, valid below ~11 km)
    pressure = P0 * (1.0 - L * elevation / T0) ** (g * M / (R * L))

    # Ideal gas law using the actual air temperature
    temperature_k = temperature + 273.15
    density = pressure * M / (R * temperature_k)

    return density


def dryAirDensity(elevationMeters: int|float = 0, tempCelsius: float = 0) -> float:
    """
    Return dry air density in kg/m^3
    slightly faster version based on full version
    """
    p = ((1.0 - .0065 * elevationMeters / 288.15) ** 5.255933)
    return p * 2934.899 / (8.31446 * (tempCelsius + 273.15))


def densityTest():
    # elev m, temp C, expected output
    testVals = [
        [0,    -15, 1.367],
        [0,     15, 1.225],
        [0,     35, 1.146],
        [1000,   0, 1.146],
        [1000,  20, 1.068],
        [2000,  10, 0.978],
        [2000,  30, 0.913],
        [3000,  -5, 5.911],
        [3000,  15, 0.848],
    ]
    for e in testVals:
        # error is less than .5% in both versions
        assert (dryAirDensityFull(e[0], e[1]) / e[2]) - 1 < .005
        assert (dryAirDensity(e[0], e[1]) / e[2]) - 1 < .005

if __name__ == "__main__":
    # test ensures accuracy
    densityTest()
