/**
 * @file main.c
 * @author Mit Bailey (mitbailey99@gmail.com)
 * @brief
 * @version See Git tags for version information.
 * @date 2022.04.08
 *
 * @copyright Copyright (c) 2022
 *
 */

#include "gpiodev.h"
#include "meb_print.h"
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <time.h>

char *get_date()
{
    static char buf[10];
    time_t t = time(NULL);
    struct tm dt = *localtime(&t);
    snprintf(buf, sizeof(buf), "%04d%02d%02d", dt.tm_year + 1900, dt.tm_mon + 1, dt.tm_mday);
    return buf;
}

char *get_time()
{
    static char buf[10];
    time_t t = time(NULL);
    struct tm dt = *localtime(&t);
    snprintf(buf, sizeof(buf), "%02d%02d%02d", dt.tm_hour, dt.tm_min, dt.tm_sec);
    return buf;
}

int check_make_dir(char *prefix, char *loc, int size)
{
    char dir[256];
    int dirsz = snprintf(dir, sizeof(dir), "%s/%s/%s", prefix, get_date(), get_time());
    char cmd[256];
    snprintf(cmd, sizeof(cmd), "mkdir -p %s", dir);
    int res = system(cmd);
    if (!res)
    {
        if (size < dirsz + 1)
        {
            dbprintlf("Not enough memory to copy output directory");
        }
        else
        {
            memcpy(loc, dir, dirsz + 1);
        }
    }
    return res;
}

volatile sig_atomic_t done = 0;

void sighandler(int sig)
{
    done = 1;
}

static char default_pref[11] = {
    0,
};

#define TRIGIN 11
#define TRIGOUT 13

int main(int argc, char *argv[])
{
    if (argc < 4 || argc > 5)
    {
        printf("Usage:\n%s <Set name> <Scan Wait time (ms)> <Exposure (ms)> [number of snaps]\n\nNote: Exposure is taken every 0.5 seconds, or 1.1 * exposure time, whichever is greater.\n\n", argv[0]);
        exit(0);
    }
    int set_num = 0;
    char *name_pref = NULL;
    if (strlen(argv[1]) == 0 || strlen(argv[1]) > 10)
    {
        for (int i = 0; i < 10; i++)
            default_pref[i] = (rand() % 26) + (rand() % 2 ? 'A' : 'a');
        default_pref[10] = '\0';
        name_pref = default_pref;
    }
    else
    {
        name_pref = argv[1];
    }
    int wait_time = atoi(argv[2]);
    if (wait_time < 0)
        wait_time = 120 * 1000;
    if (wait_time > 10 * 60 * 1000)
        wait_time = 10 * 60 * 1000;
    int exposure = atoi(argv[3]);
    if (exposure < 0)
        exposure = 10000;   // 10 ms
    if (exposure > 2000000) // 2 s
        exposure = 2000000;
    int count = 0;
    if (argc == 5)
        count = atoi(argv[4]);
    if (count < 10)
        count = 10;
    if (count > 100)
        count = 100;
    signal(SIGINT, sighandler);
    gpioSetMode(TRIGIN, GPIO_IRQ_RISE);
    gpioSetPullUpDown(TRIGIN, GPIO_PUD_DOWN);
    gpioSetMode(TRIGOUT, GPIO_OUT);
    // make dir for scan
    char dirloc[256];
    memset(dirloc, 0x0, sizeof(dirloc));
    check_make_dir("/home/pi/CamTrigger/data", dirloc, sizeof(dirloc));
    int tout_count = 0;
    while (!done)
    {
        dbprintlf("Waiting");
        int retval = gpioWaitIRQ(TRIGIN, GPIO_IRQ_RISE, wait_time);

        if (retval > 0)
        {
            tout_count = 0;
            // Interrupt
            // Run capture_image.py
            bprintlf("Starting image capture...");
            char cmd[512];
            snprintf(cmd, sizeof(cmd), "python3 /home/pi/CamTrigger/src/capture_image.py %s/%s_%d %d %d", dirloc, name_pref, set_num++, exposure, count);
            system(cmd);
            dbprintlf("Pulsing");
            gpioWrite(TRIGOUT, GPIO_HIGH);
            usleep(10000); // 10 ms
            gpioWrite(TRIGOUT, GPIO_LOW);
        }
        else if (retval < -1)
        {
            // Error
            dbprintlf(FATAL "Encountered an error (%d) when waiting for an interrupt!", retval);
            return retval;
        }
        else
        {
            dbprintlf("Timed out, looping to wait again.");
            tout_count++;
        }
        if (tout_count >= 10) // allow 10 timeouts
            break;
    }

    return 0;
}
