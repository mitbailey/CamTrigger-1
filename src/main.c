/**
 * @file main.c
 * @author your name (you@domain.com)
 * @brief 
 * @version 0.1
 * @date 2022-04-13
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
#include <netdb.h>
#include <sys/socket.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

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
volatile sig_atomic_t sigpipe = 0;
void sigPipeHandler(int sig)
{
    sigpipe = 1;
}

static char default_pref[11] = {
    0,
};

#define TRIGIN 11
#define TRIGOUT 13

int main(int argc, char *argv[])
{
    if (argc < 4 || argc > 6)
    {
        printf("Usage:\n%s <Set name> <Scan Wait time (ms)> <Exposure (ms)> [number of snaps] [Gain]\n\nNote: Exposure is taken every 0.5 seconds, or 1.1 * exposure time, whichever is greater.\n\n", argv[0]);
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
    if (argc >= 5)
        count = atoi(argv[4]);
    if (count < 5)
        count = 5;
    if (count > 100)
        count = 100;
    int gain = 10;
    if (argc == 6)
        gain = atoi(argv[5]);
    if (gain < 6)
        gain = 6;
    if (gain > 1023)
        gain = 1023;
    signal(SIGINT, sighandler);
    signal(SIGPIPE, sigPipeHandler);
    gpioSetMode(TRIGIN, GPIO_IRQ_RISE);
    gpioSetPullUpDown(TRIGIN, GPIO_PUD_DOWN);
    gpioSetMode(TRIGOUT, GPIO_OUT);
    // make dir for scan
    char dirloc[256];
    memset(dirloc, 0x0, sizeof(dirloc));
    check_make_dir("/home/pi/CamTrigger/data", dirloc, sizeof(dirloc));
    int tout_count = 0;

    // socket stuff
    int sockfd = -1, connfd = -1;
    struct sockaddr_in servaddr, cli;
    bzero(&servaddr, sizeof(servaddr));
    // assign IP and port
    servaddr.sin_family = AF_INET;
    servaddr.sin_addr.s_addr = inet_addr("127.0.0.1");
    servaddr.sin_port = htons(65432);

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
            char base_cmd[512];
            snprintf(base_cmd, sizeof(base_cmd), " %s/%s_%d %d %d %d", dirloc, name_pref, set_num++, exposure, count, gain);
            char full_cmd[1024];
            snprintf(full_cmd, sizeof(full_cmd), "%04d%s", strlen(base_cmd), base_cmd);
            bprintlf("Sending command: %s", full_cmd);
            sigpipe = 0;
            sockfd = socket(AF_INET, SOCK_STREAM, 0);
            if (sockfd == -1)
            {
                dbprintlf("Could not create socket");
                goto move_on;
            }
            if (connect(sockfd, (struct sockaddr *)&servaddr, sizeof(servaddr)) != 0)
            {
                dbprintlf("Could not connect to server");
                goto move_on;
            }
            else
            {
                int sz = 0;
                if (done) goto move_on;
                do
                {
                    int out = send(sockfd, full_cmd + sz, strlen(full_cmd + sz), 0);
                    if (out == -1)
                    {

                    }
                    else
                        sz += out;
                    if (sigpipe)
                    {
                        goto move_on;
                    }
                } while (sz < strlen(full_cmd) && !done);
                sz = 0;
                char tmp[10];
                memset(tmp, 0x0, sizeof(tmp));
                if (done) goto move_on;
                do
                {
                    int in = recv(sockfd, tmp + sz, 5 - sz, MSG_WAITFORONE);
                    if (in == -1)
                    {

                    }
                    else
                    {
                        sz += in;
                    }
                    if (sigpipe)
                    {
                        goto move_on;
                    }
                } while (sz < 5 && !done);
                if (strlen(tmp) == 5 && strcmp(tmp, "DONE!") == 0)
                {
                    bprintlf("Gathered data!");
                }
                else if (strlen(tmp) == 5 && strcmp(tmp, "ERROR") == 0)
                {
                    bprintlf("Error gathering data.");
                }
                else if (strlen(tmp) < sizeof(tmp))
                {
                    bprintlf("Received: %s", tmp);
                }
            }
move_on:
            if (sockfd != -1)
            {
                close(sockfd);
                sockfd = -1;
            }
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
        if (tout_count >= 2) // allow 10 timeouts
            break;
    }

    return 0;
}
