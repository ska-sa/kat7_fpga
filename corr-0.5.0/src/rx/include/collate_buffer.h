#ifndef COLLATE_BUFFER_H
#define COLLATE_BUFFER_H

#include <netinet/in.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <sys/types.h>
#include <netdb.h>
#include <dirent.h>
#include <sys/param.h>
#include <sys/stat.h>
#include <signal.h>

#define N_BYTES         4
#define NOTIME          -1
#define MAX_REJECT      100
#define X_PER_F         2
#define ADC_RATE        100000000
#define TIME_SCALE      128
#define ACC_RANGE       2

//ACC_RANGE is seconds around current timestamp which should be accepted as valid timestamps.
//ADC_RATE is ADC sample rate in Hz. Used for scaling timestamps from correlator.
//TIME_SCALE is a scaling factor to get correlator timestamps to ADC samples.

typedef struct {
    int32_t *buf;
    int *flagbuf;
    int buflen;
    int *xeng_ai_order;
    int *xeng_aj_order;
    int nant;
    int nbl;
    int nchan;
    int npol;
    int nwin;
    int sdisp;
    int acc_len;
    uint64_t sync_time;
    int64_t cur_t; // Change from uint64_t to int64_t is intentional
    int rd_win;
    int n_reject;
    int (*callback)(int,int,int,int64_t,float *,int *, int, void *);
    int (*sdisp_callback)(int, int,int,int,int64_t,float *,int *, int, void *);
    void *userdata;
} CollateBuffer;
    
void init_collate_buffer(CollateBuffer *cb, int nant, int nchan, int npol, int nwin, int sdisp, char *sdisp_destination_ip, int acc_len);
void free_collate_buffer(CollateBuffer cb);
//int default_callback(int i, int j, int pol, double t, float *data, int *flags, int nchan, void *userdata);
int default_callback(int i, int j, int pol, int64_t t, float *data, int *flags, int nchan, void *userdata);
int sdisp_callback(int corr_prod_id, int i, int j, int pol, int64_t t, float *data, int *flags, int nchan, void *userdata);
void set_cb_callback(CollateBuffer *cb, int (*callback)(int,int,int,int64_t,float *,int *,int,void *));
void set_cb_sdisp_callback(CollateBuffer *cb, int (*sdisp_callback)(int,int,int,int,int64_t,float *,int *,int,void *));
int collate_packet(CollateBuffer *cb, CorrPacket pkt);

#endif
