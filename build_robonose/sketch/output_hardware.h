#line 1 "D:\\PBL6\\thudata\\PBL6\\firmware\\RoboNose_Dataset_S3\\output_hardware.h"
#pragma once
#include <stdint.h>
bool initializeOutputHardware();
bool writePumpDuty(uint16_t logicalDuty);
void writeValveOutput(bool energized);
