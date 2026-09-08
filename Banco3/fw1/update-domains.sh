#!/bin/sh

nft flush set inet filter blocked_domains

while read domain; do
   for ip in $(dig +short A "$domain"); do
       nft add element inet filter blocked_domains { $ip }
   done
done < /etc/domain-control/blocked.txt
