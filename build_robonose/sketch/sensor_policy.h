#line 1 "D:\\PBL6\\thudata\\PBL6\\firmware\\RoboNose_Dataset_S3\\sensor_policy.h"
#pragma once
#include <stdint.h>
namespace SensorPolicy {
inline bool fresh(uint8_t fields,uint8_t status) { return fields>0&&(status&0x80)!=0; }
}
