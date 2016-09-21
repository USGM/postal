tracking_response = u"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
   <s:Body>
      <ShipmentTrackingResponse xmlns="http://ws.aramex.net/ShippingAPI/v1/">
         <Transaction xmlns:i="http://www.w3.org/2001/XMLSchema-instance" i:nil="true"/>
         <Notifications xmlns:i="http://www.w3.org/2001/XMLSchema-instance"/>
         <HasErrors>false</HasErrors>
         <TrackingResults xmlns:i="http://www.w3.org/2001/XMLSchema-instance" xmlns:a="http://schemas.microsoft.com/2003/10/Serialization/Arrays">
            <a:KeyValueOfstringArrayOfTrackingResultmFAkxlpY>
               <a:Key>123456</a:Key>
               <a:Value>
                  <TrackingResult>
                     <WaybillNumber>123456</WaybillNumber>
                     <UpdateCode>SH001</UpdateCode>
                     <UpdateDescription>Shipment received at destination warehouse</UpdateDescription>
                     <UpdateDateTime>2016-05-31T16:00:00</UpdateDateTime>
                     <UpdateLocation>JOHANNESBURG, South Africa</UpdateLocation>
                     <Comments/>
                     <ProblemCode/>
                     <GrossWeight>540</GrossWeight>
                     <ChargeableWeight>540</ChargeableWeight>
                     <WeightUnit>KG</WeightUnit>
                  </TrackingResult>
               </a:Value>
            </a:KeyValueOfstringArrayOfTrackingResultmFAkxlpY>
         </TrackingResults>
         <NonExistingWaybills xmlns:i="http://www.w3.org/2001/XMLSchema-instance" xmlns:a="http://schemas.microsoft.com/2003/10/Serialization/Arrays"/>
      </ShipmentTrackingResponse>
   </s:Body>
</s:Envelope>
"""