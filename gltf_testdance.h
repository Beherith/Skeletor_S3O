// This file is meant to be included in two different units, e.g. armwar and armwarV2, and perform the same action sequence.
// Compile this file without GLTF axis-remapping flags or macros. Current
// RecoilEngine versions load GLTF piece data into the same model coordinate
// frame as S3O, so this action must move identically on equivalent models.


#ifndef TESTPIECE
    #define TESTPIECE torso
#endif


GLTFTestDance(){
    // tilt forward
    turn TESTPIECE to x-axis <45> speed <90>;
    sleep 500;
    turn TESTPIECE to x-axis <0> speed <90>;
    sleep 500;

    // turn left
    turn TESTPIECE to y-axis <45> speed <90>;
    sleep 500;
    turn TESTPIECE to y-axis <0> speed <90>;
    sleep 500;

    // tilt left
    turn TESTPIECE to z-axis <45> speed <90>;
    sleep 500;
    turn TESTPIECE to z-axis <0> speed <90>;
    sleep 500;

    // move right 
    move TESTPIECE to x-axis [10] speed [20];
    sleep 500;
    move TESTPIECE to x-axis [0] speed [20];
    sleep 500;

    //move up
    move TESTPIECE to y-axis [10] speed [20];
    sleep 500;
    move TESTPIECE to y-axis [0] speed [20];
    sleep 500;

    // move forward
    move TESTPIECE to z-axis [10] speed [20];
    sleep 500;
    move TESTPIECE to z-axis [0] speed [20];
    sleep 500;

}
