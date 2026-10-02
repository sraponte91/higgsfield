import cv2,numpy as np
ld=lambda k: cv2.imread('tl1/sd4k/f%03d.png'%k,cv2.IMREAD_UNCHANGED).astype(np.float32)/65535
sm=lambda x: cv2.resize(x,(1080,1920),interpolation=cv2.INTER_AREA)
a,b=ld(25),ld(26)
sa,sb=sm(a),sm(b)
G=(cv2.GaussianBlur(sb,(0,0),12)+0.01)/(cv2.GaussianBlur(sa,(0,0),12)+0.01)
G=np.clip(G,0.4,3.0)
sift=cv2.SIFT_create(4000)
g8=lambda x: (cv2.cvtColor(x,cv2.COLOR_BGR2GRAY)*255).astype(np.uint8)
kr,dr=sift.detectAndCompute(g8(sa),None)
for k in range(1,26):
    f=ld(k); sf=sm(f)
    kf,df=sift.detectAndCompute(g8(sf),None)
    good=[m for m,n in cv2.BFMatcher().knnMatch(dr,df,k=2) if m.distance<0.75*n.distance]
    src=np.float32([kr[m.queryIdx].pt for m in good]).reshape(-1,1,2); dst=np.float32([kf[m.trainIdx].pt for m in good]).reshape(-1,1,2)
    H,inl=cv2.findHomography(src,dst,cv2.RANSAC,3.0)
    Gk=cv2.warpPerspective(G,H,(1080,1920),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
    Gk=cv2.resize(Gk,(f.shape[1],f.shape[0]),interpolation=cv2.INTER_CUBIC)
    out=np.clip(f*Gk,0,1)
    cv2.imwrite('tl1/sd4k/f%03d.png'%k,(out*65535+0.5).astype(np.uint16))
    print(k,int(inl.sum()),'inliers')
