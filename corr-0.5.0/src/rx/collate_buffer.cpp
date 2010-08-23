#include "include/corr_packet.h"
#include "include/collate_buffer.h"
#include "include/sdisp.h"

// A callback receives per-baseline spectra and metadata
// "data" and "flags" are pointers to buffers of length 2*nchan and nchan,
// respectively, that have been
// malloc'd just for this purpose.  The callback assumes responsibility for
// freeing these buffers when finished.  Failure to do so opens a major
// memory leak!
int default_callback(int ai, int aj, int pol, int64_t t,
        float *data, int *flags, int nchan, void *userdata) {
    int i, nflagged=0;
    for (i=0; i < nchan; i++) {
        nflagged += flags[i];
    }
    printf("    (%d,%d),pol=%d,time=%ld: %d/%d channels flagged in default callback\n", 
        ai, aj, pol, t, nflagged, nchan);
    free(data); free(flags);
    return 0;
}

void send_sdisp_packet(uint8_t *sdisp_packet, int send_size) {
 //fprintf(stderr,"Sdisp packet send has size %i\n", send_size);
 char **i = sdisp_ips;
 usleep(500);
 while (*i) {
  listener_addr.sin_addr.s_addr = inet_addr(*i);
  if ((sendto(sock, sdisp_packet, send_size, 0, (struct sockaddr *) &listener_addr, sizeof(listener_addr))) != send_size) {
   perror("sendto() sent incorrect number of bytes");
   exit(1);
  }
  i++;
 }
 // and send to the default sdisp ip as well...
 if ((sendto(sock, sdisp_packet, send_size, 0, (struct sockaddr *) &base_addr, sizeof(base_addr))) != send_size) {
  perror("sendto() sent incorrect number of bytes");
  exit(1);
 }
}

// Callback to generate Fringe finder compatible signal display packets.
// Each packet(s) should contain a complete set of frequency channels for a particular correlation product.
// Each unique combination of ai, aj and pol is a correlation product.

int sdisp_callback(int corr_prod_id, int ai, int aj, int pol, int64_t t,
        float *data, int *flags, int nchan, void *userdata) {
 int i, data_length, offset, ch;
 float *sdc, *s_iter;
 struct sdisp_header *sdh;
  // header for each packet
 uint8_t *sdisp_packet;
 //if (corr_prod_id > 2) return 0;
 data_length = nchan * 2 * sizeof(float);
 sdc = 0;
 sdisp_packet = (uint8_t *) malloc(SDISP_PACKET_SIZE + sizeof(struct sdisp_header));
 //fprintf(stderr, "Generating sdisp packets for ai %i, aj %i, pol %i\n", ai, aj, pol);
 for (ch = 0; ch < nchan; ch++) {
   offset = ch * 2 * sizeof(float);
   if (offset % SDISP_PACKET_SIZE == 0) {
    memset(sdisp_packet, 0, SDISP_PACKET_SIZE + sizeof(struct sdisp_header));
     // reuse the packet
    sdh = (struct sdisp_header *) (sdisp_packet);
    sdh->magic_number = htons(SDISP_MAGIC);
    sdh->length = htons(data_length);
    sdh->corr_product_id = htons(corr_prod_id);
    sdh->offset = htons(offset);
    sdh->timestamp_ms = t;
    //fprintf(stderr, "Corr prod id: %i (%i, %i, %i), Packet timestamp is: %lu\n", corr_prod_id, ai, aj, pol, t);
    sdc = (float *) (sdisp_packet + sizeof(struct sdisp_header));
   }
   for (i=0; i < 2; i++) {
    //pd = (float *) (sdisp_data_frame + (ch * num_baselines));
    s_iter = (float *) (data + (ch * 2) + i);
    *sdc = *s_iter; // / received_dumps;
    //if (corr_prod_id == 0) fprintf(stderr,"Ch: %i, Data: %f\n", ch, *s_iter);
    sdc++;
   } 
    // send a packet if it is full
   if ((offset + sizeof(double)) % SDISP_PACKET_SIZE == 0) {
    //fprintf(stderr,"Sent full packet at channel %i\n", ch);
    send_sdisp_packet(sdisp_packet, SDISP_PACKET_SIZE + sizeof(struct sdisp_header));
     // send a full packet worth of data
   }
  } // end of for each channel
  if (data_length % SDISP_PACKET_SIZE > 0) {
   //fprintf(stderr,"Sending remainder sdisp packet\n");
    // send the dangling packet...
   send_sdisp_packet(sdisp_packet, data_length % SDISP_PACKET_SIZE + sizeof(struct sdisp_header));
  }
 free(sdisp_packet); 
 return 0;
}

void init_collate_buffer(CollateBuffer *cb, int nant, int nchan, int npol, int nwin, int sdisp, char *sdisp_destination_ip, int acc_len) {
    // Initialize a CollateBuffer
    int i, j, k, cnt=0, loop_pnt, flag, c;
    cb->nant = nant;
    cb->nbl = nant * (nant + 1) / 2;
    cb->xeng_ai_order = (int *)malloc(cb->nbl * sizeof(int));
    if (cb->xeng_ai_order == NULL) 
        throw PacketError("Malloc error in init_collate_buffer()");
    cb->xeng_aj_order = (int *)malloc(cb->nbl * sizeof(int));
    if (cb->xeng_aj_order == NULL)
        throw PacketError("Malloc error in init_collate_buffer()");
    cb->nchan = nchan;
    cb->npol = npol;
    cb->nwin = nwin;
    cb->sdisp = sdisp;
    cb->acc_len = acc_len;
    cb->sync_time = 0;
    cb->buflen = 2 * cb->nbl * nchan * npol * nwin;
    cb->cur_t = NOTIME;
    set_cb_callback(cb, &default_callback);
    if (sdisp) set_cb_sdisp_callback(cb, &sdisp_callback);
    cb->userdata = NULL;

    // setup signal display addresses
    if ((sock = socket(PF_INET, SOCK_DGRAM, IPPROTO_UDP)) < 0) {
     perror("socket() failed");
     exit(1);
    }

    memset(&base_addr, 0, sizeof(base_addr));
    base_addr.sin_family = AF_INET;
    base_addr.sin_addr.s_addr = inet_addr(sdisp_destination_ip);
    base_addr.sin_port = htons(7006);

    memset(&listener_addr, 0, sizeof(listener_addr));
    listener_addr.sin_family = AF_INET;
    listener_addr.sin_addr.s_addr = inet_addr(sdisp_destination_ip);
    listener_addr.sin_port = htons(7006);
    
    // Dynamically allocate our big buffer
    cb->buf = (int32_t *)malloc(cb->buflen * sizeof(int32_t));
    cb->flagbuf = (int *)malloc(cb->buflen/2 * sizeof(int));
    if (cb->buf == NULL || cb->flagbuf == NULL)
        throw PacketError("Malloc error in init_collate_buffer()");

    // Initialize flagbuf to all flagged (flags are removed as data arrives)
    for (i=0; i < cb->buflen/2; i++) {
        cb->flagbuf[i] = 1;
    }
    // Initialize cb->xeng_a[ij]_order with the order that baselines appear out
    // of a CASPER X Engine.  These buffers are used for collating packet data
    // First list non-loopback Baselines
    for (i=0; i < nant; i++) {
        for (j=nant/2; j >= 0; j--) {
            k = ((i > j) ? (i - j) : (i - j)+nant) % nant;
            if (i >= k) {
                cb->xeng_ai_order[cnt] = k;
                cb->xeng_aj_order[cnt] = i;
                cnt++;
            }
        }
    }
    // Then list loopback baselines only if they haven't been listed already
    loop_pnt = cnt;
    for (i=0; i < nant; i++) {
        for (j=nant/2; j >= 0; j--) {
            k = ((i > j) ? (i - j) : (i - j)+nant) % nant;
            if (i < k) {
                // Make sure we didn't count this baseline in the first loop
                flag = 0;
                for (c=0; c < loop_pnt; c++) {
                    if ((cb->xeng_ai_order[c] == i) && 
                            (cb->xeng_aj_order[c] == k)) {
                        flag = 1;
                        break;
                    }
                }
                if (!flag) {
                    cb->xeng_ai_order[cnt] = (uint16_t) i;
                    cb->xeng_aj_order[cnt] = (uint16_t) k;
                    cnt++;
                }
            }
        }
    }
}

void free_collate_buffer(CollateBuffer cb) {
    // Free all memory allocated for a CollateBuffer
    free(cb.xeng_ai_order);
    free(cb.xeng_aj_order);
    free(cb.buf);
    free(cb.flagbuf);
}

void set_cb_sdisp_callback(CollateBuffer *cb,
        int (*cb_func)(int, int,int,int,int64_t,float *,int *,int, void *)) {
    cb->sdisp_callback = cb_func;
}

void set_cb_callback(CollateBuffer *cb, 
        int (*cb_func)(int,int,int,int64_t,float *,int *,int, void *)) {
    cb->callback = cb_func;
}
#define HASHBL(i,j) (i + j*(j+1)/2)
#define ADDR(cb,i,j,pol,ch,win) \
    (2*(HASHBL(i,j) + cb.nbl*(pol + cb.npol*(ch + cb.nchan*(win)))))

int xids[8] = {0,0,0,0,0,0,0,0};
int packet_count = 0;
time_t ppt = 0;
// Put an incoming packet in the correct place in memory, and initiate
// readout via a callback, which is passed cb->userdata
int collate_packet(CollateBuffer *cb, CorrPacket pkt) {
    int prev_cnt, nvals, ch_per_x;
    int bl, pol, ch;
    int64_t cnt, pkt_t, pkt_ts;
    int addr;
    int i, j, cp_id;
    float *data=NULL;
    int *flags=NULL;
    //printf("Got a packet to collate!");
    // Determine whether to accept this packet
    pkt_t = cb->sync_time*ADC_RATE  + (uint64_t)(pkt.timestamp * TIME_SCALE); //pkt_t is in ADC samples since unix epoch
    pkt_ts = pkt_t /ADC_RATE; //pkt_ts is in seconds since unix epoch

    //fprintf(stderr, "Raw packet timestamp: %lu\n", pkt.timestamp);
    //fprintf(stderr, "Packet timestamp: %lu\n", pkt_t);

    if (cb->cur_t == NOTIME) {
        // Case for not having locked onto any integration yet
        cb->cur_t = pkt_t;
        printf("Setting timelock to %ld, %s", cb->cur_t,ctime(&pkt_ts));
        cb->rd_win = 0;
        cb->n_reject = 0;
    } else if (pkt_t <= cb->cur_t - cb->nwin*ACC_RANGE*ADC_RATE || pkt_t > cb->cur_t + cb->nwin*ACC_RANGE*ADC_RATE) {
        // Case for locked on integration and rx out-of-range pkt
        printf("Rejecting packet with timestamp %ld\ni.", pkt_t);
        printf(" Timelock at %ld, accepting (%ld,%ld]\n", 
                cb->cur_t, cb->cur_t - cb->nwin*ACC_RANGE*ADC_RATE, cb->cur_t + cb->nwin*ACC_RANGE*ADC_RATE);
        cb->n_reject += 1;
        if (cb->n_reject > MAX_REJECT) {
            printf("Too many packet rejections: Resetting timelock.\n");
            cb->cur_t = NOTIME;
        }
        return 0;
    } else if (pkt_t > cb->cur_t) {
        // Case for locked on integration and rx in-range pkt w/ new time - time to read out an integration window.
        printf("Reading out window %d.\n", cb->rd_win);
        for (pol=0; pol < cb->npol; pol++) {
          cp_id = pol;
          for (j=0; j < cb->nant; j++) {
            for (i=0; i <= j; i++) {
                // Dynamically allocate spectrum buffers
                data = (float *)malloc(2*cb->nchan * sizeof(float));
                flags = (int *)malloc(cb->nchan * sizeof(int));
                if (data == NULL || flags == NULL)
                    throw PacketError("Malloc error in collate_packet()");
                for (ch=0; ch < cb->nchan; ch++) {
                    addr = ADDR((*cb),i,j,pol,ch,cb->rd_win);
                    //Scale data back to 4bit*4bit values, and correct for PAPER's reversed channel order.
                    data[2*((cb->nchan -1) - ch)] = (float) cb->buf[addr] / cb->acc_len;
                    data[2*((cb->nchan -1) - ch)+1] = (float) cb->buf[addr+1] / cb->acc_len;
                    flags[((cb->nchan -1) - ch)] = cb->flagbuf[addr/2];
                    //data[2*ch] = (float) cb->buf[addr];
                    //data[2*ch+1] = (float) cb->buf[addr+1];
                    //if (i ==0 && j == 0 && pol == 0 && ch > 500 && ch < 520) fprintf(stderr,"Scaled Window Ch:%i, D1: %f, D2: %f\n", ch, data[2*ch], data[2*ch+1]);
                    //if (i <= 3 && j <= 3 && ch == 1 && (pol==0 || pol==1)) fprintf(stderr," (%i,%i, pol %i,Ch:%i) D1: %i, D2: %i\n", i,j,pol,ch, ((int32_t *)(pkt.data + cnt))[0], ((int32_t *)(pkt.data + cnt))[1]);
                    // Clear out flags for this entry
                    cb->flagbuf[addr/2] = 1;
                }
              
                if (cb->sdisp) {
                 if (cb->sdisp_callback(cp_id, i,j,pol,cb->cur_t/ADC_RATE,data,flags,cb->nchan, cb->userdata)) {
                  printf("Failed to exec sdisp callback.\n"); return 1; }
                }
            
                //if (cb->callback(i,j,pol,double(cb->cur_t)/ADC_RATE, data,flags,cb->nchan, cb->userdata)) {
                if (cb->callback(i,j,pol,cb->cur_t, data,flags,cb->nchan, cb->userdata)) {
                printf("CollateBuffer bailed on callback.\n"); return 1; }
            
            cp_id+=4;
            } // end of for i <= j
          }
        }
        cb->rd_win = (cb->rd_win + 1) % cb->nwin;
        ppt = pkt_ts;
        cb->cur_t=pkt_t;
        printf("Advancing timelock to %ld, %s", cb->cur_t, ctime(&ppt));
    } // end if we're done reading out this timestamp

    // When packet is accepted, reset the rejection counter
    cb->n_reject = 0;
    ch_per_x = (cb->nchan / cb->nant) * X_PER_F;
    prev_cnt = pkt.heap_off / N_BYTES / 2;
    // Step through packet data and copy it into the CollateBuffer buffer
    for (cnt=0; cnt < pkt.pktinfo.len; cnt += N_BYTES*2) {
        nvals = (cnt + pkt.heap_off) / (N_BYTES * 2); //starting position in complex numbers. (complex values received thus far for this integration)
        // Decode the data order
        pol = nvals % cb->npol;
        bl = (nvals / cb->npol) % cb->nbl;
        i = cb->xeng_ai_order[bl];
        j = cb->xeng_aj_order[bl];
        ch = (nvals / cb->npol / cb->nbl) % ch_per_x; //freq channel on this xeng.
        //ch = ch * cb->nant + pkt.instids.engine_id;
        ch = ch * (cb->nant /X_PER_F) + pkt.instids.engine_id;
        //printf("Got %i bytes at offset %i for xeng %i. pol=%i, bl=%i,i=%i,j=%i,ch=%i.\n",pkt.pktinfo.len,pkt.heap_off,pkt.instids.engine_id,pol,bl,i,j,ch); 
        //            if (ch == 0) fprintf(stderr," (%i,%i, pol %i,Ch:%i) D1: %i, D2: %i\n", i,j,pol,ch, ((int32_t *)(pkt.data + cnt))[0], ((int32_t *)(pkt.data + cnt))[1]);
        
        //printf("Ch %i calc: (%i / %i / %i) mod %i . %i + %i)\n", ch, nvals, cb->npol, cb->nbl, ch_per_x, cb->nant, pkt.instids.engine_id);
        // Put this data in the appropriate place in the buffer
        //FORFEIT windows. only using one at a time. If you get a packet from the next timestamp, we move on, assuming that all data from the previous one was received.
        addr = ADDR((*cb),i,j,pol,ch, cb->rd_win);
        if (addr+1 > cb->buflen)
            throw PacketError("Addr outside buffer space in collate_packet()");
        // Copy real and then imaginary part
        cb->buf[addr] = ((int32_t *)(pkt.data + cnt))[0];
        cb->buf[addr+1] = ((int32_t *)(pkt.data + cnt))[1];
        // Register that we got this data
        cb->flagbuf[addr/2] = 0;
        xids[pkt.instids.engine_id]++;
        packet_count++;
        //if (packet_count % 500000 == 0) printf("X Engine Packet Counts: 0:%i, 1:%i, 2:%i, 3:%i, 4:%i, 5:%i, 6:%i, 7:%i\n", xids[0], xids[1], xids[2], xids[3], xids[4], xids[5], xids[6], xids[7]);
        //if (pol == 0 && i == 0 && j == 0 && (ch > 509 && ch < 515)) {
        //    printf("Got packet: (xid=%d,pol=%d,i=%d,j=%d,ch=%d,addr=%d,real=%i,imag=%i)\n", pkt.instids.engine_id,pol, i, j, ch, addr, cb->buf[addr], cb->buf[addr+1]);
        //}
        //printf("real=%d,imag=%d\n", cb->buf[addr], cb->buf[addr+1]);
    }
    return 0;
}    
