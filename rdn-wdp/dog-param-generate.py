#!/usr/bin/env python3

for sigma in range(10,31,2):
    for div in [1.5,2,3,4]:
        for radius in [2,3,5,7,10]:
            for cutoff in [0,0.125,0.25]:
                print(str(sigma) + "," + str(div) + "," + str(radius) + "," + str(cutoff))
